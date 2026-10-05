import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";
import { decodeFrame, encodeAck, encodeMessage } from "../src/codec.ts";
import type { DashboardConfig } from "../src/types.ts";

declare global {
  interface Window {
    __serialWrites: number[][];
    __bluetoothWrites: number[][];
    __usbWrites: number[][];
    __makeAck: (frame: Uint8Array) => Uint8Array;
    __deviceFrames: number;
  }
}

const repo = fileURLToPath(new URL("../../", import.meta.url));
const kettle = JSON.parse(
  await readFile(join(repo, "examples/smart-kettle/out/smart-kettle/dashboard.config.json"), "utf8"),
) as DashboardConfig;
const bench = JSON.parse(
  await readFile(join(repo, "examples/bench-meter/out/bench-meter/dashboard.config.json"), "utf8"),
) as DashboardConfig;
const kettleStatus = kettle.contract.protocol.messages.find((message) => message.name === "status")!;
const setTarget = kettle.contract.protocol.messages.find((message) => message.name === "set_target")!;
const startBoil = kettle.contract.protocol.messages.find((message) => message.name === "start_boil")!;
const sample = bench.contract.protocol.messages.find((message) => message.name === "sample")!;
const setRange = bench.contract.protocol.messages.find((message) => message.name === "set_range")!;
const targetAck = encodeAck(setTarget.id, 0, 0, 1);
const rangeAck = encodeAck(setRange.id, 0, 0, 1);
const kettleFrame = encodeMessage(
  kettleStatus,
  { water_temp_c: 23.5, target_temp_c: 60, heating: false, error_code: 0 },
  6,
);
const sampleFrame = encodeMessage(sample, { voltage_mv: 12000, current_ua: 500000, temperature_c: 23.4 }, 7);

async function openKettle(page: Page): Promise<void> {
  await page.goto("/smart-kettle/out/smart-kettle/");
  await expect(page.locator("#diagnostics")).toContainText('"platform": "linux"');
  await expect(page.getByRole("heading", { name: "Not available in this browser" })).toBeVisible();
  await expect(page.locator("#connection-panel")).toContainText("Connect via Web Serial (chrome)");
  const unavailable = page.locator("#connection-panel ul[aria-labelledby='unavailable-routes-heading']");
  await expect(unavailable).toContainText("Tauri Bluetooth (tauri): Declared for tauri, not chrome.");
  await expect(unavailable).not.toContainText("kettle-tauri-ble");
}

async function connectVia(page: Page, config: DashboardConfig, kind: string): Promise<void> {
  const transport = config.contract.transports.find((item) => item.kind === kind);
  if (!transport) throw new Error(`Missing ${kind} transport in ${config.contract.name}`);
  await page.locator(`#connection-panel button[data-transport="${transport.id}"]`).click();
}

async function mockSerial(page: Page): Promise<void> {
  await page.addInitScript((initialFrame: number[]) => {
    window.__serialWrites = [];
    let reader: ReadableStreamDefaultController<Uint8Array> | undefined;
    window.__makeAck = (frame) => {
      const encoded = frame.at(-1) === 0 ? frame.slice(0, -1) : frame;
      const payload: number[] = [];
      for (let cursor = 0; cursor < encoded.length;) {
        const code = encoded[cursor++];
        if (!code) break;
        const end = cursor + code - 1;
        while (cursor < end) payload.push(encoded[cursor++]!);
        if (code < 255 && cursor < encoded.length) payload.push(0);
      }
      const raw = new Uint8Array([255, 1, payload[0]!, payload[1]!, 0, 0, 0]);
      let crc = 0xffff;
      for (const byte of raw.slice(0, 5)) {
        crc ^= byte << 8;
        for (let bit = 0; bit < 8; bit += 1) {
          crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
        }
      }
      raw[5] = crc & 0xff;
      raw[6] = crc >> 8;
      const result = new Uint8Array(raw.length + 2);
      let codeIndex = 0;
      let write = 1;
      let codeValue = 1;
      for (const byte of raw) {
        if (!byte) {
          result[codeIndex] = codeValue;
          codeIndex = write++;
          codeValue = 1;
        } else {
          result[write++] = byte;
          codeValue += 1;
        }
      }
      result[codeIndex] = codeValue;
      result[write] = 0;
      return result.slice(0, write + 1);
    };
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
      value: { requestPort: async () => port },
    });
  }, Array.from(kettleFrame));
}

test("mock Web Serial exchanges telemetry, commands, ACKs, and hazard confirmation", async ({ page }) => {
  await mockSerial(page);
  await openKettle(page);
  await connectVia(page, kettle, "web_serial");
  await expect(page.locator(".connection-state")).toContainText("connected");
  await expect(page.locator("output[data-message='status'][data-field='water_temp_c']")).toHaveText("23.5 °C");
  await expect(page.locator("output[data-message='status'][data-field='target_temp_c']")).toHaveText("60 °C");

  const target = page.locator(".widget").filter({ hasText: "Set target" });
  await expect(target).not.toHaveClass(/hazard/);
  const targetInput = target.getByLabel("target temp c (°C)", { exact: true });
  const targetField = setTarget.fields.find((field) => field.name === "target_temp_c")!;
  if (targetField.min !== null && targetField.min !== undefined) {
    await expect(targetInput).toHaveAttribute("min", String(targetField.min));
  }
  if (targetField.max !== null && targetField.max !== undefined) {
    await expect(targetInput).toHaveAttribute("max", String(targetField.max));
  }
  await targetInput.fill("60");
  await expect(target.locator("output[data-control-field='target_temp_c']")).toHaveText("60 °C");
  await target.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__serialWrites.length)).toBe(1);
  const command = decodeFrame(Uint8Array.from(await page.evaluate(() => window.__serialWrites[0]!)), kettle.contract.protocol.messages);
  expect(command).toMatchObject({ id: setTarget.id, values: { target_temp_c: 60 } });

  const start = page.locator(".widget").filter({ hasText: "Start boil" });
  await expect(start).toHaveClass(/hazard/);
  await expect(start.locator("button")).toHaveClass(/hazard/);
  await expect(start.getByText("Hazardous — asks for confirmation")).toBeVisible();
  page.once("dialog", (dialog) => dialog.dismiss());
  await start.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("alert")).toContainText("cancelled");
  expect(await page.evaluate(() => window.__serialWrites.length)).toBe(1);
  page.once("dialog", (dialog) => dialog.accept());
  await start.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__serialWrites.length)).toBe(2);
  expect(startBoil.id).toBeGreaterThan(0);
});

test("WebSocket carries telemetry and ACKs host commands", async ({ page }) => {
  let commandFrames = 0;
  await page.routeWebSocket(/.*/, (socket) => {
    socket.send(Buffer.from(kettleFrame));
    socket.onMessage((message) => {
      if (typeof message !== "string") {
        commandFrames += 1;
        socket.send(Buffer.from(encodeAck(setTarget.id, 0, 0, 2)));
      }
    });
  });
  await openKettle(page);
  await connectVia(page, kettle, "websocket");
  await expect(page.locator(".connection-state")).toContainText("connected");
  await expect(page.locator("output[data-message='status'][data-field='water_temp_c']")).toHaveText("23.5 °C");
  const target = page.locator(".widget").filter({ hasText: "Set target" });
  await target.locator("input[name='target_temp_c']").fill("60");
  await target.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => commandFrames).toBe(1);
});

test("mock Web Bluetooth exchanges telemetry and a framed command", async ({ page }) => {
  const transport = kettle.contract.transports.find((item) => item.kind === "web_bluetooth");
  test.skip(!transport || transport.kind !== "web_bluetooth", "example has no Bluetooth transport");
  const config = transport as Extract<(typeof kettle.contract.transports)[number], { kind: "web_bluetooth" }>;
  await page.addInitScript((data: {
    initialFrame: number[];
    ackBytes: number[];
    rxUuid: string;
    txUuid: string;
  }) => {
    const { initialFrame, ackBytes, rxUuid, txUuid } = data;
    window.__bluetoothWrites = [];
    const listeners = new Map<string, (event: { target: unknown }) => void>();
    const rx = {
      properties: { notify: true, indicate: false },
      value: null as DataView | null,
      addEventListener: (name: string, callback: (event: { target: unknown }) => void) => listeners.set(name, callback),
      removeEventListener: (name: string) => listeners.delete(name),
      async startNotifications() {
        this.value = new DataView(Uint8Array.from(initialFrame).buffer);
        listeners.get("characteristicvaluechanged")?.({ target: rx });
        return rx;
      },
      async stopNotifications() {},
    };
    const tx = {
      properties: { write: true, writeWithoutResponse: false },
      async writeValue(value: BufferSource) {
        window.__bluetoothWrites.push(Array.from(new Uint8Array(value as ArrayBuffer)));
        rx.value = new DataView(Uint8Array.from(ackBytes).buffer);
        listeners.get("characteristicvaluechanged")?.({ target: rx });
      },
    };
    const service = { getCharacteristic: async (uuid: string) => uuid === rxUuid ? rx : tx };
    const device = {
      gatt: { connected: false, async connect() { this.connected = true; return { getPrimaryService: async () => service }; }, disconnect() { this.connected = false; } },
      addEventListener() {},
      removeEventListener() {},
    };
    Object.defineProperty(navigator, "bluetooth", {
      configurable: true,
      value: { requestDevice: async () => device },
    });
  }, {
    initialFrame: Array.from(kettleFrame),
    ackBytes: Array.from(targetAck),
    rxUuid: config.rx_characteristic,
    txUuid: config.tx_characteristic,
  });
  await openKettle(page);
  await connectVia(page, kettle, "web_bluetooth");
  await expect(page.locator(".connection-state")).toContainText("connected");
  await expect(page.locator("output[data-message='status'][data-field='water_temp_c']")).toHaveText("23.5 °C");
  const target = page.locator(".widget").filter({ hasText: "Set target" });
  await target.locator("input[name='target_temp_c']").fill("60");
  await target.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__bluetoothWrites.length)).toBe(1);
});

test("mock WebUSB reads bench telemetry and writes a control frame", async ({ page }) => {
  await page.addInitScript((data: { initialFrame: number[]; ackFrame: number[] }) => {
    const { initialFrame, ackFrame } = data;
    window.__usbWrites = [];
    const queue: Array<{ status: string; data: DataView }> = [];
    const waiters: Array<(result: { status: string; data: DataView }) => void> = [];
    const feed = (bytes: Uint8Array) => {
      const result = { status: "ok", data: new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength) };
      const waiter = waiters.shift();
      if (waiter) waiter(result);
      else queue.push(result);
    };
    const device = {
      configuration: {},
      async open() {},
      async selectConfiguration() {},
      async claimInterface() {},
      async releaseInterface() {},
      async close() {},
      async transferIn() {
        if (queue.length) return queue.shift()!;
        return new Promise<{ status: string; data: DataView }>((resolve) => waiters.push(resolve));
      },
      async transferOut(_endpoint: number, bytes: BufferSource) {
        const frame = new Uint8Array(bytes as ArrayBuffer);
        window.__usbWrites.push(Array.from(frame));
        feed(Uint8Array.from(ackFrame));
        return { status: "ok" };
      },
      async clearHalt() {},
    };
    Object.defineProperty(navigator, "usb", {
      configurable: true,
      value: { requestDevice: async () => device },
    });
    feed(Uint8Array.from(initialFrame));
  }, { initialFrame: Array.from(sampleFrame), ackFrame: Array.from(rangeAck) });
  await page.goto("/bench-meter/out/bench-meter/");
  await connectVia(page, bench, "webusb");
  await expect(page.locator(".connection-state")).toContainText("connected");
  const voltageField = sample.fields.find((field) => field.name === "voltage_mv")!;
  await expect(page.locator("output[data-message='sample'][data-field='voltage_mv']")).toHaveText(
    voltageField.unit ? `12000 ${voltageField.unit}` : "12000",
  );
  const temperatureOutput = page.locator("output[data-message='sample'][data-field='temperature_c']");
  if (await temperatureOutput.count()) {
    const temperatureField = sample.fields.find((field) => field.name === "temperature_c")!;
    const renderedTemperature = (await temperatureOutput.textContent() ?? "").replace(
      temperatureField.unit ? ` ${temperatureField.unit}` : "",
      "",
    );
    expect(Number(renderedTemperature)).toBeCloseTo(23.4, 5);
    if (temperatureField.unit) {
      await expect(temperatureOutput).toContainText(` ${temperatureField.unit}`);
    }
  }
  const range = page.locator(".widget").filter({ hasText: "Set range" });
  const rangeInput = range.locator("input[name='range']");
  const rangeField = setRange.fields.find((field) => field.name === "range")!;
  if (rangeField.min !== null && rangeField.min !== undefined) {
    await expect(rangeInput).toHaveAttribute("min", String(rangeField.min));
  }
  if (rangeField.max !== null && rangeField.max !== undefined) {
    await expect(rangeInput).toHaveAttribute("max", String(rangeField.max));
  }
  await rangeInput.fill("2");
  await range.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__usbWrites.length)).toBe(1);
  expect(setRange.id).toBeGreaterThan(0);
});

test("iOS Safari is unsupported and Bluefy explains Bluetooth caveats", async ({ browser }) => {
  const safariContext = await browser.newContext({
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  });
  const safari = await safariContext.newPage();
  await safari.goto("/bench-meter/out/bench-meter/");
  await expect(safari.locator("#platform-banner")).toContainText("unsupported");
  await expect(safari.locator("#platform-banner")).toContainText("Bench meter requires WebUSB");
  await safariContext.close();

  const bluefyContext = await browser.newContext({
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Bluefy/3.0 Mobile/15E148 Safari/604.1",
  });
  await bluefyContext.addInitScript(() => {
    Object.defineProperty(navigator, "bluetooth", { configurable: true, value: {} });
  });
  const bluefy = await bluefyContext.newPage();
  await bluefy.goto("/smart-kettle/out/smart-kettle/");
  await expect(bluefy.locator("#diagnostics")).toContainText('"browser": "bluefy"');
  await expect(bluefy.locator("#caveat-notices")).toContainText(/Bluefy Web Bluetooth notifications/i);
  const ble = kettle.contract.transports.find((item) => item.kind === "web_bluetooth")!;
  await expect(bluefy.locator(`#connection-panel button[data-transport="${ble.id}"]`)).toBeVisible();
  await bluefyContext.close();
});

test("iPadOS Safari and Bluefy use the independent iPadOS declaration", async ({ browser }) => {
  const safariContext = await browser.newContext({
    userAgent: "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
  });
  const safari = await safariContext.newPage();
  await safari.goto("/bench-meter/out/bench-meter/");
  await expect(safari.locator("#diagnostics")).toContainText('"os": "ipados"');
  await expect(safari.locator("#platform-banner")).toContainText("Bench meter requires WebUSB");
  await safariContext.close();

  const bluefyContext = await browser.newContext({
    userAgent: "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Bluefy/3.0 Mobile/15E148 Safari/604.1",
  });
  await bluefyContext.addInitScript(() => {
    Object.defineProperty(navigator, "bluetooth", { configurable: true, value: {} });
  });
  const bluefy = await bluefyContext.newPage();
  await bluefy.goto("/smart-kettle/out/smart-kettle/");
  await expect(bluefy.locator("#diagnostics")).toContainText('"os": "ipados"');
  await expect(bluefy.locator("#diagnostics")).toContainText('"browser": "bluefy"');
  await expect(bluefy.locator("#caveat-notices")).toContainText(/Bluefy Web Bluetooth notifications/i);
  const ble = kettle.contract.transports.find((item) => item.kind === "web_bluetooth")!;
  await expect(bluefy.locator(`#connection-panel button[data-transport="${ble.id}"]`)).toBeVisible();
  await bluefyContext.close();
});

test("BSD diagnostics include the detected operating-system variant", async ({ browser }) => {
  const context = await browser.newContext({
    userAgent: "Mozilla/5.0 (X11; FreeBSD amd64) AppleWebKit/537.36 Chromium/154.0.8037.57 Safari/537.36",
  });
  const page = await context.newPage();
  await page.goto("/smart-kettle/out/smart-kettle/");
  await expect(page.locator("#diagnostics")).toContainText('"platform": "bsd"');
  await expect(page.locator("#diagnostics")).toContainText('"os_variant": "FreeBSD"');
  await context.close();
});

test("two browser pages establish a real WebRTC DataChannel through a signaling relay", async ({ browser }) => {
  const transport = bench.contract.transports.find((item) => item.kind === "webrtc");
  test.skip(!transport || transport.kind !== "webrtc", "example has no WebRTC transport");
  const config = structuredClone(bench);
  const peerConfig = config.contract.transports.find((item) => item.kind === "webrtc") as
    | {
      id: string;
      kind: "webrtc";
      signaling_url: string;
      data_channel: string;
      ordered: boolean;
      ice_servers: Array<{ urls: string[] }>;
    }
    | undefined;
  if (!peerConfig) throw new Error("Bench meter WebRTC transport is missing");
  peerConfig.ice_servers = [];

  const context = await browser.newContext();
  // Chromium otherwise limits ICE route enumeration in network-isolated runs.
  await context.grantPermissions(["camera", "microphone"], {
    origin: "http://127.0.0.1:4173",
  });
  const host = await context.newPage();
  const device = await context.newPage();
  await host.route("**/bench-meter/out/bench-meter/dashboard.config.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(config) }),
  );

  let deviceSocket: WebSocketRoute | undefined;
  await context.routeWebSocket(peerConfig.signaling_url, (socket) => {
    if (!deviceSocket) {
      deviceSocket = socket;
      return;
    }
    socket.onMessage((message) => deviceSocket?.send(message));
    deviceSocket.onMessage((message) => socket.send(message));
  });
  await device.goto("/health");
  await device.evaluate(async ({ signalUrl, frameBytes }) => {
    await new Promise<void>((resolve, reject) => {
      const signaling = new WebSocket(signalUrl);
      const peer = new RTCPeerConnection({ iceServers: [] });
      let remoteCandidates: RTCIceCandidateInit[] = [];
      window.__deviceFrames = 0;
      peer.addEventListener("icecandidate", (event) => {
        if (event.candidate) signaling.send(JSON.stringify({ type: "candidate", candidate: event.candidate.toJSON() }));
      });
      peer.addEventListener("datachannel", (event) => {
        const channel = event.channel;
        channel.binaryType = "arraybuffer";
        channel.addEventListener("open", () => {
          const frame = Uint8Array.from(frameBytes);
          // The answerer can observe `open` before the offerer finishes its
          // channel setup, so a single send can race host readiness and drop
          // the only sample frame. Re-send on a bounded interval instead.
          let attempts = 0;
          const resend = window.setInterval(() => {
            if (channel.readyState !== "open" || ++attempts >= 60) {
              window.clearInterval(resend);
              return;
            }
            channel.send(frame);
          }, 250);
          channel.send(frame);
        });
        channel.addEventListener("message", (message) => {
          window.__deviceFrames += 1;
          const encoded = new Uint8Array(message.data as ArrayBuffer);
          const rawBytes: number[] = [];
          const frame = encoded.at(-1) === 0 ? encoded.slice(0, -1) : encoded;
          for (let cursor = 0; cursor < frame.length;) {
            const code = frame[cursor++]!;
            const end = cursor + code - 1;
            while (cursor < end) rawBytes.push(frame[cursor++]!);
            if (code < 255 && cursor < frame.length) rawBytes.push(0);
          }
          const ack = new Uint8Array([255, 1, rawBytes[0]!, rawBytes[1]!, 0, 0, 0]);
          let crc = 0xffff;
          for (const byte of ack.slice(0, 5)) {
            crc ^= byte << 8;
            for (let bit = 0; bit < 8; bit += 1) {
              crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
            }
          }
          ack[5] = crc & 0xff;
          ack[6] = crc >> 8;
          const output = new Uint8Array(ack.length + 2);
          let codeIndex = 0;
          let write = 1;
          let code = 1;
          for (const byte of ack) {
            if (byte === 0) {
              output[codeIndex] = code;
              codeIndex = write++;
              code = 1;
            } else {
              output[write++] = byte;
              code += 1;
            }
          }
          output[codeIndex] = code;
          output[write] = 0;
          channel.send(output.slice(0, write + 1));
        });
      });
      signaling.addEventListener("message", async (event) => {
        const message = JSON.parse(String(event.data)) as { type: string; sdp?: string; candidate?: RTCIceCandidateInit };
        if (message.type === "offer" && message.sdp) {
          await peer.setRemoteDescription({ type: "offer", sdp: message.sdp });
          for (const candidate of remoteCandidates) await peer.addIceCandidate(candidate);
          remoteCandidates = [];
          const answer = await peer.createAnswer();
          await peer.setLocalDescription(answer);
          signaling.send(JSON.stringify({ type: "answer", sdp: answer.sdp }));
        } else if (message.type === "candidate" && message.candidate) {
          if (peer.remoteDescription) await peer.addIceCandidate(message.candidate);
          else remoteCandidates.push(message.candidate);
        }
      });
      signaling.addEventListener("open", () => resolve(), { once: true });
      signaling.addEventListener("error", () => reject(new Error("Device signaling socket failed")), { once: true });
    });
  }, { signalUrl: peerConfig.signaling_url, frameBytes: Array.from(sampleFrame) });
  await host.goto("/bench-meter/out/bench-meter/");
  await connectVia(host, config, "webrtc");
  await expect(host.locator(".connection-state")).toContainText("connected", { timeout: 30_000 });
  // The channel reports "connected" before the first decoded sample reaches
  // the widget, so the telemetry read needs the same headroom.
  const voltageField = sample.fields.find((field) => field.name === "voltage_mv")!;
  await expect(host.locator("output[data-message='sample'][data-field='voltage_mv']")).toHaveText(
    voltageField.unit ? `12000 ${voltageField.unit}` : "12000",
    { timeout: 30_000 },
  );
  const range = host.locator(".widget").filter({ hasText: "Set range" });
  await range.locator("input[name='range']").fill("2");
  await range.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => device.evaluate(() => window.__deviceFrames)).toBe(1);
  await context.close();
});
