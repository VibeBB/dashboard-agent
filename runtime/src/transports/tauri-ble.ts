import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";
import { getTauriBackends, isTauriRuntime, type TauriBleBackend } from "./tauri.ts";

type TauriBleConfig = Extract<TransportConfig, { kind: "tauri_ble" }>;

export interface TauriBleSelection {
  address: string;
}

export class TauriBleTransport extends BaseTransport {
  readonly kind = "tauri_ble" as const;
  readonly #config: TauriBleConfig;
  readonly #selection: TauriBleSelection | undefined;
  #backend: TauriBleBackend | null = null;
  #connected = false;
  #subscribed = false;

  constructor(config: TauriBleConfig, selection?: TauriBleSelection) {
    super();
    this.#config = config;
    this.#selection = selection;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const backend = getTauriBackends().ble;
    if (!backend || !isTauriRuntime()) throw new Error("Tauri BLE backend is unavailable");
    if (!this.#selection?.address) throw new Error("Select a Bluetooth device before connecting");
    this.#backend = backend;
    await backend.connect(this.#selection.address, () => {
      this.#connected = false;
      this.#subscribed = false;
      this.closeHandler();
    });
    this.#connected = true;
    rejectIfAborted(signal);
    await backend.subscribe(
      this.#config.rx_characteristic,
      this.#config.service_uuid,
      (data) => this.acceptBytes(Uint8Array.from(data)),
    );
    this.#subscribed = true;
    rejectIfAborted(signal);
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#backend || !this.#connected) throw new Error("Tauri BLE transport is not connected");
    await this.#backend.send(
      this.#config.tx_characteristic,
      Array.from(frame),
      "withResponse",
      this.#config.service_uuid,
    );
  }

  async close(): Promise<void> {
    const backend = this.#backend;
    this.#backend = null;
    if (this.#subscribed) {
      await backend?.unsubscribe(
        this.#config.rx_characteristic,
        this.#config.service_uuid,
      ).catch(() => undefined);
    }
    this.#subscribed = false;
    if (this.#connected) await backend?.disconnect().catch(() => undefined);
    this.#connected = false;
  }
}
