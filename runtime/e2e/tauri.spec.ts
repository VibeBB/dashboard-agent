import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { decodeFrame, encodeMessage } from "../src/codec.ts";
import type { TauriBackends } from "../src/transports/tauri.ts";
import type { DashboardConfig } from "../src/types.ts";

declare global {
  interface Window {
    __TAURI_INTERNALS__: Record<string, unknown>;
    __TAURI_BACKENDS__: TauriBackends;
    __tauriBleWrites: number[][];
    __tauriDisconnect: (() => void) | null;
  }
}

const repo = fileURLToPath(new URL("../../", import.meta.url));
const config = JSON.parse(
  await readFile(join(repo, "examples/smart-kettle/out/smart-kettle/dashboard.config.json"), "utf8"),
) as DashboardConfig;
const status = config.contract.protocol.messages.find((message) => message.name === "status")!;
const setTarget = config.contract.protocol.messages.find((message) => message.name === "set_target")!;
const initialFrame = encodeMessage(
  status,
  { water_temp_c: 23.5, target_temp_c: 60, heating: false, error_code: 0 },
  6,
);

test("Tauri picker connects a filtered device, shows telemetry, and writes a command", async ({ page }) => {
  await page.addInitScript((frame: number[]) => {
    window.__TAURI_INTERNALS__ = {};
    window.__tauriBleWrites = [];
    window.__tauriDisconnect = null;
    window.__TAURI_BACKENDS__ = {
      ble: {
        async startScan(handler) {
          handler([
            {
              address: "kettle-1",
              name: "Kettle One",
              services: ["12345678-1234-5678-1234-56789abcdef0"],
            },
            {
              address: "other-1",
              name: "Other device",
              services: ["12345678-1234-5678-1234-56789abcdef0"],
            },
            {
              address: "kettle-2",
              name: "Kettle Missing Service",
              services: ["0000180d-0000-1000-8000-00805f9b34fb"],
            },
          ]);
        },
        async stopScan() {},
        async connect(_address, onDisconnect) {
          window.__tauriDisconnect = onDisconnect;
        },
        async disconnect() {
          window.__tauriDisconnect?.();
        },
        async subscribe(_characteristic, _service, handler) {
          handler(frame);
        },
        async unsubscribe() {},
        async send(_characteristic, data) {
          window.__tauriBleWrites.push(data);
        },
      },
    };
  }, Array.from(initialFrame));

  await page.goto("/smart-kettle/out/smart-kettle/");
  await expect(page.locator("#diagnostics")).toContainText('"browser": "tauri"');
  await expect(page.locator("#diagnostics")).toContainText('"os": "linux"');
  await page.getByRole("button", { name: "Scan for Bluetooth devices" }).click();

  const picker = page.getByLabel("Bluetooth device");
  await expect(picker).toBeEnabled();
  const optionLabels = await picker.locator("option").allTextContents();
  expect(optionLabels.some((label) => label.includes("Kettle One"))).toBe(true);
  expect(optionLabels.some((label) => label.includes("Other device"))).toBe(false);
  expect(optionLabels.some((label) => label.includes("Missing Service"))).toBe(false);
  await picker.selectOption("kettle-1");
  await page.locator('#connection-panel button[data-transport="kettle-tauri-ble"]').click();
  await expect(page.locator(".connection-state")).toContainText("connected");
  await expect(page.locator("output[data-message='status'][data-field='water_temp_c']")).toHaveText("23.5");

  const target = page.locator(".widget").filter({ hasText: "Set target" });
  await target.locator("input[name='target_temp_c']").fill("60");
  await target.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__tauriBleWrites.length)).toBe(1);
  const commandFrame = await page.evaluate(() => window.__tauriBleWrites[0]!);
  expect(decodeFrame(Uint8Array.from(commandFrame), config.contract.protocol.messages))
    .toMatchObject({ id: setTarget.id, values: { target_temp_c: 60 } });
});
