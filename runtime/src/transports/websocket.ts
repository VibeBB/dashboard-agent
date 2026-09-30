import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";

type WebSocketConfig = Extract<TransportConfig, { kind: "websocket" }>;

export class WebSocketTransport extends BaseTransport {
  readonly kind = "websocket" as const;
  private readonly config: WebSocketConfig;
  #socket: WebSocket | null = null;

  constructor(config: WebSocketConfig) {
    super();
    this.config = config;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const socket = new WebSocket(this.config.url, this.config.subprotocol ?? undefined);
    this.#socket = socket;
    socket.binaryType = "arraybuffer";
    socket.addEventListener("message", (event: MessageEvent<ArrayBuffer | Blob>) => {
      if (event.data instanceof ArrayBuffer) this.frameHandler(new Uint8Array(event.data));
      else if (event.data instanceof Blob) void event.data.arrayBuffer().then((data) => this.frameHandler(new Uint8Array(data)));
    });
    await new Promise<void>((resolve, reject) => {
      const failed = (): void => reject(new Error("WebSocket connection failed"));
      const aborted = (): void => {
        socket.close();
        reject(new DOMException("The operation was aborted", "AbortError"));
      };
      socket.addEventListener("open", () => {
        socket.removeEventListener("error", failed);
        signal.removeEventListener("abort", aborted);
        resolve();
      }, { once: true });
      socket.addEventListener("error", failed, { once: true });
      socket.addEventListener("close", () => this.closeHandler());
      signal.addEventListener("abort", aborted, { once: true });
    });
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#socket || this.#socket.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket transport is not connected");
    }
    const copy = new Uint8Array(frame.length);
    copy.set(frame);
    this.#socket.send(copy);
  }

  async close(): Promise<void> {
    this.#socket?.close();
    this.#socket = null;
  }
}
