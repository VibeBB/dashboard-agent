import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";

type BluetoothConfig = Extract<TransportConfig, { kind: "web_bluetooth" }>;

export class WebBluetoothTransport extends BaseTransport {
  readonly kind = "web_bluetooth" as const;
  private readonly config: BluetoothConfig;
  #device: BluetoothDevice | null = null;
  #tx: BluetoothRemoteGATTCharacteristic | null = null;
  #rx: BluetoothRemoteGATTCharacteristic | null = null;
  #disconnect = (): void => this.closeHandler();
  #notification = (event: Event): void => {
    const characteristic = event.target as BluetoothRemoteGATTCharacteristic;
    if (characteristic.value) {
      this.acceptBytes(new Uint8Array(
        characteristic.value.buffer,
        characteristic.value.byteOffset,
        characteristic.value.byteLength,
      ));
    }
  };

  constructor(config: BluetoothConfig) {
    super();
    this.config = config;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const filter: BluetoothLEScanFilter = {
      services: [this.config.service_uuid],
      ...(this.config.name_prefix ? { namePrefix: this.config.name_prefix } : {}),
    };
    const device = await navigator.bluetooth.requestDevice({ filters: [filter] });
    rejectIfAborted(signal);
    if (!device.gatt) throw new Error("Selected Bluetooth device does not expose GATT");
    this.#device = device;
    device.addEventListener("gattserverdisconnected", this.#disconnect);
    const server = await device.gatt.connect();
    rejectIfAborted(signal);
    const service = await server.getPrimaryService(this.config.service_uuid);
    const [rx, tx] = await Promise.all([
      service.getCharacteristic(this.config.rx_characteristic),
      service.getCharacteristic(this.config.tx_characteristic),
    ]);
    if (!rx.properties.notify && !rx.properties.indicate) {
      throw new Error("Bluetooth RX characteristic must notify or indicate");
    }
    if (!tx.properties.write && !tx.properties.writeWithoutResponse) {
      throw new Error("Bluetooth TX characteristic must support write");
    }
    this.#rx = rx;
    this.#tx = tx;
    rx.addEventListener("characteristicvaluechanged", this.#notification);
    await rx.startNotifications();
    rejectIfAborted(signal);
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#tx) throw new Error("Bluetooth transport is not connected");
    for (let offset = 0; offset < frame.length; offset += 20) {
      await this.#tx.writeValue(frame.slice(offset, offset + 20));
    }
  }

  async close(): Promise<void> {
    if (this.#rx) {
      this.#rx.removeEventListener("characteristicvaluechanged", this.#notification);
      try {
        await this.#rx.stopNotifications();
      } catch {
        this.#rx = null;
      }
    }
    this.#device?.removeEventListener("gattserverdisconnected", this.#disconnect);
    if (this.#device?.gatt?.connected) this.#device.gatt.disconnect();
    this.#device = null;
    this.#tx = null;
    this.#rx = null;
  }
}
