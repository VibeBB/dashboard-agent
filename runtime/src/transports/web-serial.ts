import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";

type WebSerialConfig = Extract<TransportConfig, { kind: "web_serial" }>;

export class WebSerialTransport extends BaseTransport {
  readonly kind = "web_serial" as const;
  private readonly config: WebSerialConfig;
  #port: SerialPort | null = null;
  #readerAbort: AbortController | null = null;
  #writer: WritableStreamDefaultWriter<Uint8Array> | null = null;

  constructor(config: WebSerialConfig) {
    super();
    this.config = config;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const filter: SerialPortFilter = {};
    if (this.config.usb_vendor_id !== null && this.config.usb_vendor_id !== undefined) {
      filter.usbVendorId = this.config.usb_vendor_id;
    }
    if (this.config.usb_product_id !== null && this.config.usb_product_id !== undefined) {
      filter.usbProductId = this.config.usb_product_id;
    }
    const options: SerialPortRequestOptions = { filters: [filter] };
    if (this.config.bluetooth_service_class_id) {
      options.allowedBluetoothServiceClassIds = [this.config.bluetooth_service_class_id];
    }
    const port = await navigator.serial.requestPort(options);
    rejectIfAborted(signal);
    this.#port = port;
    await port.open({ baudRate: this.config.baud_rate });
    if (!port.readable || !port.writable) throw new Error("Serial port streams are unavailable");
    this.#writer = port.writable.getWriter();
    this.#readerAbort = new AbortController();
    signal.addEventListener("abort", () => this.#readerAbort?.abort(), { once: true });
    void this.#readLoop(port.readable, this.#readerAbort.signal);
  }

  async #readLoop(stream: ReadableStream<Uint8Array>, signal: AbortSignal): Promise<void> {
    const reader = stream.getReader();
    try {
      while (!signal.aborted) {
        const result = await reader.read();
        if (result.done) break;
        if (result.value) this.acceptBytes(result.value);
      }
    } catch {
      if (!signal.aborted) this.closeHandler();
    } finally {
      reader.releaseLock();
    }
    if (!signal.aborted) this.closeHandler();
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#writer) throw new Error("Serial transport is not connected");
    await this.#writer.write(frame);
  }

  async close(): Promise<void> {
    this.#readerAbort?.abort();
    await this.#writer?.close().catch(() => undefined);
    this.#writer?.releaseLock();
    if (this.#port) await this.#port.close().catch(() => undefined);
    this.#writer = null;
    this.#port = null;
    this.#readerAbort = null;
  }
}
