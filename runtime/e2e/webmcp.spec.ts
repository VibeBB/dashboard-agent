import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { encodeAck, encodeMessage } from "../src/codec.ts";
import type { DashboardConfig } from "../src/types.ts";

declare global {
  interface Window {
    __serialRequests: number;
    __serialWrites: number[][];
    __makeAck: (frame: Uint8Array) => Uint8Array;
  }
}

const repo = fileURLToPath(new URL("../../", import.meta.url));
const kettle = JSON.parse(await readFile(join(repo, "examples/smart-kettle/out/smart-kettle/dashboard.config.json"), "utf8")) as DashboardConfig;
const bench = JSON.parse(await readFile(join(repo, "examples/bench-meter/out/bench-meter/dashboard.config.json"), "utf8")) as DashboardConfig;
const telemetry = kettle.contract.protocol.messages.find((message) => message.name === "status")!;
const setTarget = kettle.contract.protocol.messages.find((message) => message.name === "set_target")!;
const startBoil = kettle.contract.protocol.messages.find((message) => message.name === "start_boil")!;
const telemetryFrame = encodeMessage(
  telemetry,
  { water_temp_c: 23.5, target_temp_c: 60, heating: false, error_code: 0 },
  6,
);

async function connectSerial(page: Page): Promise<void> {
  const transport = kettle.contract.transports.find((item) => item.kind === "web_serial")!;
  await page.locator(`#connection-panel button[data-transport="${transport.id}"]`).click();
}

async function mockSerial(page: Page): Promise<void> {
  await page.addInitScript((initialFrame) => {
    window.__serialRequests = 0;
    window.__serialWrites = [];
    let reader: ReadableStreamDefaultController<Uint8Array> | undefined;
    const port = {
      readable: new ReadableStream<Uint8Array>({ start(controller) { reader = controller; } }),
      writable: new WritableStream<Uint8Array>({
        write(chunk) {
          window.__serialWrites.push(Array.from(chunk));
          reader?.enqueue(window.__makeAck(new Uint8Array(chunk)));
        },
      }),
      async open() { setTimeout(() => reader?.enqueue(Uint8Array.from(initialFrame)), 0); },
      async close() {},
    };
    Object.defineProperty(navigator, "serial", {
      configurable: true,
      value: {
        requestPort: async () => {
          window.__serialRequests += 1;
          return port;
        },
      },
    });
    window.__makeAck = (frame) => {
      const encodedFrame = frame.at(-1) === 0 ? frame.slice(0, -1) : frame;
      const payload = [];
      for (let cursor = 0; cursor < encodedFrame.length;) {
        const code = encodedFrame[cursor++];
        if (!code) break;
        const end = cursor + code - 1;
        while (cursor < end) payload.push(encodedFrame[cursor++]);
        if (code < 255 && cursor < encodedFrame.length) payload.push(0);
      }
      const raw = new Uint8Array([255, 1, payload[0] ?? 0, payload[1] ?? 0, 0, 0, 0]);
      let crc = 0xffff;
      for (const byte of raw.slice(0, 5)) {
        crc ^= byte << 8;
        for (let bit = 0; bit < 8; bit += 1) crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
      }
      raw[5] = crc & 0xff;
      raw[6] = crc >> 8;
      const encoded = new Uint8Array(raw.length + 2);
      let codeIndex = 0;
      let write = 1;
      let codeValue = 1;
      for (const byte of raw) {
        if (!byte) {
          encoded[codeIndex] = codeValue;
          codeIndex = write++;
          codeValue = 1;
        } else {
          encoded[write++] = byte;
          codeValue += 1;
        }
      }
      encoded[codeIndex] = codeValue;
      encoded[write] = 0;
      return encoded.slice(0, write + 1);
    };
  }, Array.from(telemetryFrame));
}

test("smart-kettle exposes the expected WebMCP tools and device operations", async ({ page }) => {
  await mockSerial(page);
  await page.goto("/smart-kettle/out/smart-kettle/");
  await expect(page.locator("#diagnostics")).toContainText('"webmcp": true');
  const names = await page.evaluate(async () => (await document.modelContext!.getTools!()).map((tool) => tool.name));
  expect(names).toEqual(["dashboard_status", "read_telemetry", "send_set_target", "send_start_boil"]);

  const beforeConnect = page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "send_set_target")!;
    return document.modelContext!.executeTool!(tool, JSON.stringify({ target_temp_c: 55 }));
  });
  await expect(beforeConnect).rejects.toThrow(/UnknownError/);
  expect(await page.evaluate(() => window.__serialRequests)).toBe(0);
  expect(await page.evaluate(() => window.__serialWrites.length)).toBe(0);

  await connectSerial(page);
  await expect(page.locator(".connection-state")).toContainText("connected");
  const readResult = await page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "read_telemetry")!;
    return JSON.parse(await document.modelContext!.executeTool!(tool, "{}"));
  });
  expect(readResult.messages.status.values.water_temp_c).toBe(23.5);

  const sendResult = page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "send_set_target")!;
    return JSON.parse(await document.modelContext!.executeTool!(tool, JSON.stringify({ target_temp_c: 55 })));
  });
  expect(await sendResult).toEqual({ sent: true, acked: true, seq: 0 });

  const accepted = page.waitForEvent("dialog").then((dialog) => dialog.accept());
  const hazardResult = page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "send_start_boil")!;
    return JSON.parse(await document.modelContext!.executeTool!(tool, "{}"));
  });
  await accepted;
  expect(await hazardResult).toMatchObject({ sent: true, acked: true });

  const dismiss = page.waitForEvent("dialog").then((dialog) => dialog.dismiss());
  const cancelled = page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "send_start_boil")!;
    return document.modelContext!.executeTool!(tool, "{}");
  });
  await dismiss;
  await expect(cancelled).rejects.toThrow(/UnknownError/);
  expect(await page.evaluate(() => window.__serialWrites.length)).toBe(2);
  expect(setTarget.id).toBeGreaterThan(0);
  expect(startBoil.id).toBeGreaterThan(0);
  expect(encodeAck(setTarget.id, 0, 0, 1).at(-1)).toBe(0);
});

test("bench-meter exposes only the two read-only WebMCP tools", async ({ page }) => {
  await page.goto("/bench-meter/out/bench-meter/");
  await expect(page.locator("#diagnostics")).toContainText('"webmcp": true');
  const names = await page.evaluate(async () => (await document.modelContext!.getTools!()).map((tool) => tool.name));
  expect(names).toEqual(["dashboard_status", "read_telemetry"]);
  const annotations = await page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    return tools.map((tool) => ({ name: tool.name, annotations: tool.annotations }));
  });
  expect(annotations.find((tool) => tool.name === "dashboard_status")?.annotations.readOnlyHint).toBe(true);
  expect(annotations.find((tool) => tool.name === "read_telemetry")?.annotations.untrustedContentHint).toBe(true);
  const status = await page.evaluate(async () => {
    const tools = await document.modelContext!.getTools!();
    const tool = tools.find((item) => item.name === "dashboard_status")!;
    return JSON.parse(await document.modelContext!.executeTool!(tool, "{}"));
  });
  expect(status.instruction).toMatch(/click Connect/i);
});
