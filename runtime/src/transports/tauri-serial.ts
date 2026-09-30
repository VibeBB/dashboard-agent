import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";
import { getTauriBackends, isTauriRuntime, type TauriSerialPort } from "./tauri.ts";

type TauriSerialConfig = Extract<TransportConfig, { kind: "tauri_serial" }>;

export interface TauriSerialSelection {
  path: string;
}

export class TauriSerialTransport extends BaseTransport {
  readonly kind = "tauri_serial" as const;
  readonly #config: TauriSerialConfig;
  readonly #selection: TauriSerialSelection | undefined;
  #port: TauriSerialPort | null = null;
  #watchHandle: { unwatch(): Promise<void> } | null = null;

  constructor(config: TauriSerialConfig, selection?: TauriSerialSelection) {
    super();
    this.#config = config;
    this.#selection = selection;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const backend = getTauriBackends().serial;
    if (!backend || !isTauriRuntime()) throw new Error("Tauri serial backend is unavailable");
    if (!this.#selection?.path) throw new Error("Select a serial port before connecting");
    const port = new backend.SerialPort({
      path: this.#selection.path,
      baudRate: this.#config.baud_rate,
    });
    this.#port = port;
    await port.open();
    rejectIfAborted(signal);
    this.#watchHandle = await port.watch({
      onData: (data) => {
        const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
        this.acceptBytes(bytes);
      },
      onDisconnect: () => {
        void this.close().then(() => this.closeHandler());
      },
      onError: () => {
        void this.close().then(() => this.closeHandler());
      },
    }, { decode: false });
    rejectIfAborted(signal);
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#port) throw new Error("Tauri serial transport is not connected");
    const written = await this.#port.writeBinary(frame);
    if (written !== frame.length) throw new Error(`Tauri serial wrote ${written} of ${frame.length} bytes`);
  }

  async close(): Promise<void> {
    const watchHandle = this.#watchHandle;
    this.#watchHandle = null;
    await watchHandle?.unwatch().catch(() => undefined);
    const port = this.#port;
    this.#port = null;
    await port?.close().catch(() => undefined);
  }
}
