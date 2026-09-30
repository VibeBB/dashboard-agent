import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";

type WebUsbConfig = Extract<TransportConfig, { kind: "webusb" }>;

export class WebUsbTransport extends BaseTransport {
  readonly kind = "webusb" as const;
  private readonly config: WebUsbConfig;
  #device: USBDevice | null = null;
  #readerAbort: AbortController | null = null;

  constructor(config: WebUsbConfig) {
    super();
    this.config = config;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const filter: USBDeviceFilter = {
      vendorId: this.config.vendor_id,
      classCode: this.config.interface_class,
    };
    if (this.config.product_id !== null && this.config.product_id !== undefined) {
      filter.productId = this.config.product_id;
    }
    const device = await navigator.usb.requestDevice({ filters: [filter] });
    rejectIfAborted(signal);
    this.#device = device;
    await device.open();
    if (device.configuration === null) await device.selectConfiguration(1);
    await device.claimInterface(this.config.interface_number);
    this.#readerAbort = new AbortController();
    signal.addEventListener("abort", () => this.#readerAbort?.abort(), { once: true });
    void this.#readLoop(this.#readerAbort.signal);
  }

  async #readLoop(signal: AbortSignal): Promise<void> {
    while (!signal.aborted && this.#device) {
      const result = await this.#device.transferIn(this.config.endpoint_in, 64);
      if (result.status === "ok" && result.data) {
        this.acceptBytes(new Uint8Array(result.data.buffer, result.data.byteOffset, result.data.byteLength));
      } else if (result.status === "stall") {
        await this.#device.clearHalt("in", this.config.endpoint_in);
      } else {
        break;
      }
    }
    if (!signal.aborted) this.closeHandler();
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#device) throw new Error("WebUSB transport is not connected");
    const copy = new Uint8Array(frame.length);
    copy.set(frame);
    const result = await this.#device.transferOut(this.config.endpoint_out, copy);
    if (result.status !== "ok") throw new Error(`WebUSB transfer failed: ${result.status}`);
  }

  async close(): Promise<void> {
    this.#readerAbort?.abort();
    if (this.#device?.opened) {
      try {
        await this.#device.releaseInterface(this.config.interface_number);
      } finally {
        await this.#device.close();
      }
    }
    this.#readerAbort = null;
    this.#device = null;
  }
}
