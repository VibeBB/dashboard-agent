import type { TransportConfig } from "../types.ts";
import { WebBluetoothTransport } from "./web-bluetooth.ts";
import { WebRtcTransport } from "./webrtc.ts";
import { WebSerialTransport } from "./web-serial.ts";
import { WebSocketTransport } from "./websocket.ts";
import { WebUsbTransport } from "./webusb.ts";
import type { Transport as TransportInstance } from "./transport.ts";

export function createTransport(config: TransportConfig): TransportInstance {
  switch (config.kind) {
    case "web_bluetooth": return new WebBluetoothTransport(config);
    case "webusb": return new WebUsbTransport(config);
    case "web_serial": return new WebSerialTransport(config);
    case "websocket": return new WebSocketTransport(config);
    case "webrtc": return new WebRtcTransport(config);
  }
  throw new Error("Unsupported transport configuration");
}

export type { Transport as Transport } from "./transport.ts";
