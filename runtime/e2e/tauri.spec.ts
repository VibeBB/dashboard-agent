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
    __tauriPermissionAsked: boolean | undefined;
    __tauriScanCount: number;
    __tauriScanActive: boolean;
    __tauriScanWindowElapsed: boolean;
    __tauriStopScanAfterWindow: boolean;
    __tauriStopScanCount: number;
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
    window.__tauriPermissionAsked = undefined;
    window.__tauriScanCount = 0;
    window.__tauriScanActive = false;
    window.__tauriScanWindowElapsed = false;
    window.__tauriStopScanAfterWindow = false;
    window.__tauriStopScanCount = 0;
    window.__TAURI_BACKENDS__ = {
      ble: {
        async checkPermissions(askIfDenied) {
          window.__tauriPermissionAsked = askIfDenied;
          return true;
        },
        async startScan(handler, timeout) {
          window.__tauriScanCount += 1;
          window.__tauriScanActive = true;
          window.setTimeout(() => {
            if (window.__tauriScanActive) {
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
            }
          }, 25);
          window.setTimeout(() => {
            if (window.__tauriScanActive) window.__tauriScanWindowElapsed = true;
          }, timeout);
        },
        async stopScan() {
          window.__tauriStopScanAfterWindow = window.__tauriScanWindowElapsed;
          window.__tauriStopScanCount += 1;
          window.__tauriScanActive = false;
        },
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
  expect(await page.evaluate(() => window.__tauriPermissionAsked)).toBe(true);
  expect(await page.evaluate(() => window.__tauriScanCount)).toBe(1);
  expect(await page.evaluate(() => window.__tauriStopScanAfterWindow)).toBe(true);
  expect(await page.evaluate(() => window.__tauriStopScanCount)).toBe(1);
  const optionLabels = await picker.locator("option").allTextContents();
  expect(optionLabels.some((label) => label.includes("Kettle One"))).toBe(true);
  expect(optionLabels.some((label) => label.includes("Other device"))).toBe(false);
  expect(optionLabels.some((label) => label.includes("Missing Service"))).toBe(false);
  await picker.selectOption("kettle-1");
  await page.locator('#connection-panel button[data-transport="kettle-tauri-ble"]').click();
  await expect(page.locator(".connection-state")).toContainText("connected");
  await expect(page.locator("output[data-message='status'][data-field='water_temp_c']")).toHaveText("23.5 °C");

  const target = page.locator(".widget").filter({ hasText: "Set target" });
  await target.locator("input[name='target_temp_c']").fill("60");
  await target.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => page.evaluate(() => window.__tauriBleWrites.length)).toBe(1);
  const commandFrame = await page.evaluate(() => window.__tauriBleWrites[0]!);
  expect(decodeFrame(Uint8Array.from(commandFrame), config.contract.protocol.messages))
    .toMatchObject({ id: setTarget.id, values: { target_temp_c: 60 } });
});

test("Tauri BLE picker reports denied permission without starting a scan", async ({ page }) => {
  await page.addInitScript(() => {
    window.__TAURI_INTERNALS__ = {};
    window.__tauriPermissionAsked = undefined;
    window.__tauriScanCount = 0;
    window.__TAURI_BACKENDS__ = {
      ble: {
        async checkPermissions(askIfDenied) {
          window.__tauriPermissionAsked = askIfDenied;
          return false;
        },
        async startScan() {
          window.__tauriScanCount += 1;
        },
        async stopScan() {},
        async connect() {},
        async disconnect() {},
        async subscribe() {},
        async unsubscribe() {},
        async send() {},
      },
    };
  });

  await page.goto("/smart-kettle/out/smart-kettle/");
  await page.getByRole("button", { name: "Scan for Bluetooth devices" }).click();
  await expect(page.getByRole("alert")).toHaveText("Bluetooth permission denied");
  expect(await page.evaluate(() => window.__tauriPermissionAsked)).toBe(true);
  expect(await page.evaluate(() => window.__tauriScanCount)).toBe(0);
});

test("Tauri BLE picker can cancel the scan window", async ({ page }) => {
  await page.addInitScript(() => {
    window.__TAURI_INTERNALS__ = {};
    window.__tauriScanActive = false;
    window.__tauriScanWindowElapsed = false;
    window.__tauriStopScanAfterWindow = false;
    window.__tauriStopScanCount = 0;
    window.__TAURI_BACKENDS__ = {
      ble: {
        async checkPermissions() {
          return true;
        },
        async startScan(_handler, timeout) {
          window.__tauriScanActive = true;
          window.setTimeout(() => {
            if (window.__tauriScanActive) window.__tauriScanWindowElapsed = true;
          }, timeout);
        },
        async stopScan() {
          window.__tauriStopScanAfterWindow = window.__tauriScanWindowElapsed;
          window.__tauriStopScanCount += 1;
          window.__tauriScanActive = false;
        },
        async connect() {},
        async disconnect() {},
        async subscribe() {},
        async unsubscribe() {},
        async send() {},
      },
    };
  });

  await page.goto("/smart-kettle/out/smart-kettle/");
  await page.getByRole("button", { name: "Scan for Bluetooth devices" }).click();
  const cancel = page.getByRole("button", { name: "Cancel Bluetooth scan" });
  await expect(cancel).toBeEnabled();
  await cancel.click();
  await expect(page.getByRole("button", { name: "Scan for Bluetooth devices" })).toBeVisible();
  expect(await page.evaluate(() => window.__tauriStopScanCount)).toBe(1);
  expect(await page.evaluate(() => window.__tauriStopScanAfterWindow)).toBe(false);
});
