import type { TransportConfig } from "../types.ts";

export interface TauriBleDevice {
  address: string;
  name: string;
  services: string[];
}

export interface TauriBleBackend {
  checkPermissions(askIfDenied?: boolean): Promise<boolean>;
  startScan(handler: (devices: TauriBleDevice[]) => void, timeout: number): Promise<void>;
  stopScan(): Promise<void>;
  connect(address: string, onDisconnect: (() => void) | null): Promise<void>;
  disconnect(): Promise<void>;
  subscribe(
    characteristic: string,
    service: string | null,
    handler: (data: number[]) => void,
  ): Promise<void>;
  unsubscribe(characteristic: string, service?: string): Promise<void>;
  send(
    characteristic: string,
    data: number[],
    writeType?: "withResponse" | "withoutResponse",
    service?: string,
  ): Promise<void>;
}

export interface TauriPortInfo {
  path: string;
  manufacturer: string;
  pid: string;
  product: string;
  serial_number: string;
  type: string;
  vid: string;
}

export interface TauriSerialPort {
  open(): Promise<string>;
  watch(
    handlers: {
      onData: (data: string | Uint8Array) => void;
      onDisconnect?: (reason: string) => void;
      onError?: (message: string) => void;
    },
    options?: { decode?: boolean },
  ): Promise<{ unwatch(): Promise<void> }>;
  close(): Promise<void>;
  writeBinary(value: Uint8Array | number[]): Promise<number>;
}

export interface TauriSerialBackend {
  SerialPort: {
    new(options: { path: string; baudRate: number }): TauriSerialPort;
    available_ports(): Promise<Record<string, TauriPortInfo>>;
  };
}

export interface TauriBackends {
  ble?: TauriBleBackend;
  serial?: TauriSerialBackend;
}

type TauriDeviceConfig = Extract<TransportConfig, { kind: "tauri_ble" }>;
type TauriSerialConfig = Extract<TransportConfig, { kind: "tauri_serial" }>;
type TauriGlobals = typeof globalThis & {
  __TAURI_BACKENDS__?: TauriBackends;
};

let registeredBackends: TauriBackends | null = null;

export function registerTauriBackends(backends: TauriBackends): void {
  registeredBackends = { ...backends };
}

export function registerInjectedTauriBackends(): void {
  const injected = (globalThis as TauriGlobals).__TAURI_BACKENDS__;
  if (injected) registerTauriBackends(injected);
}

export function getTauriBackends(): Readonly<TauriBackends> {
  return registeredBackends ?? {};
}

export function isTauriRuntime(): boolean {
  return registeredBackends !== null && "__TAURI_INTERNALS__" in globalThis;
}

export function hasTauriBackend(kind: "tauri_ble" | "tauri_serial"): boolean {
  if (!isTauriRuntime()) return false;
  return kind === "tauri_ble" ? Boolean(registeredBackends?.ble) : Boolean(registeredBackends?.serial);
}

function normalizeBluetoothUuid(value: string): string {
  const normalized = value.toLowerCase().replace(/^0x/, "");
  if (/^[0-9a-f]{4}$/.test(normalized)) {
    return `0000${normalized}-0000-1000-8000-00805f9b34fb`;
  }
  if (/^[0-9a-f]{8}$/.test(normalized)) {
    return `${normalized}-0000-1000-8000-00805f9b34fb`;
  }
  return normalized;
}

export function filterTauriBleDevices(
  devices: TauriBleDevice[],
  config: TauriDeviceConfig,
): TauriBleDevice[] {
  const service = normalizeBluetoothUuid(config.service_uuid);
  return devices.filter((device) => {
    if (config.name_prefix && !device.name.startsWith(config.name_prefix)) return false;
    return device.services.some((candidate) => normalizeBluetoothUuid(candidate) === service);
  });
}

function matchesUsbId(actual: string, expected: number | null | undefined): boolean {
  if (expected === null || expected === undefined) return true;
  if (!actual || actual === "Unknown") return false;
  const value = actual.trim().toLowerCase();
  if (/^(0|[1-9]\d*)$/.test(value)) return Number(value) === expected;
  if (/^0x[0-9a-f]{4}$/.test(value)) return Number.parseInt(value.slice(2), 16) === expected;
  return false;
}

export function filterTauriSerialPorts(
  ports: Record<string, TauriPortInfo>,
  config: TauriSerialConfig,
): TauriPortInfo[] {
  return Object.values(ports).filter((port) =>
    port.path !== "Unknown" &&
    matchesUsbId(port.vid, config.usb_vendor_id) &&
    matchesUsbId(port.pid, config.usb_product_id)
  );
}
