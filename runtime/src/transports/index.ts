import type { TransportConfig } from "../types.ts";
import { WebBluetoothTransport } from "./web-bluetooth.ts";
import { WebRtcTransport } from "./webrtc.ts";
import { WebSerialTransport } from "./web-serial.ts";
import { WebSocketTransport } from "./websocket.ts";
import { WebUsbTransport } from "./webusb.ts";
import { TauriBleTransport } from "./tauri-ble.ts";
import { TauriSerialTransport } from "./tauri-serial.ts";
import type { Transport as TransportInstance } from "./transport.ts";

export type TauriTransportSelection = { address: string } | { path: string };

export function createTransport(
  config: TransportConfig,
  selection?: TauriTransportSelection,
): TransportInstance {
  switch (config.kind) {
    case "web_bluetooth": return new WebBluetoothTransport(config);
    case "webusb": return new WebUsbTransport(config);
    case "web_serial": return new WebSerialTransport(config);
    case "websocket": return new WebSocketTransport(config);
    case "webrtc": return new WebRtcTransport(config);
    case "tauri_ble":
      return new TauriBleTransport(
        config,
        selection && "address" in selection ? selection : undefined,
      );
    case "tauri_serial":
      return new TauriSerialTransport(
        config,
        selection && "path" in selection ? selection : undefined,
      );
  }
  throw new Error("Unsupported transport configuration");
}

export type { Transport as Transport } from "./transport.ts";
