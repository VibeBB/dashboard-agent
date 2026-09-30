import type { TransportConfig } from "../types.ts";
import { BaseTransport, rejectIfAborted } from "./transport.ts";

type WebRtcConfig = Extract<TransportConfig, { kind: "webrtc" }>;

type SignalMessage =
  | { type: "offer"; sdp: string }
  | { type: "answer"; sdp: string }
  | { type: "candidate"; candidate: RTCIceCandidateInit }
  | { type: "bye" };

function isSignalMessage(value: unknown): value is SignalMessage {
  if (typeof value !== "object" || value === null || !("type" in value)) return false;
  const type = (value as { type?: unknown }).type;
  return type === "offer" || type === "answer" || type === "candidate" || type === "bye";
}

export class WebRtcTransport extends BaseTransport {
  readonly kind = "webrtc" as const;
  private readonly config: WebRtcConfig;
  #socket: WebSocket | null = null;
  #peer: RTCPeerConnection | null = null;
  #channel: RTCDataChannel | null = null;
  #candidates: RTCIceCandidateInit[] = [];

  constructor(config: WebRtcConfig) {
    super();
    this.config = config;
  }

  async open(signal: AbortSignal): Promise<void> {
    rejectIfAborted(signal);
    const peer = new RTCPeerConnection({ iceServers: this.config.ice_servers });
    const socket = new WebSocket(this.config.signaling_url);
    this.#peer = peer;
    this.#socket = socket;
    this.#channel = peer.createDataChannel(this.config.data_channel, { ordered: this.config.ordered });
    this.#channel.binaryType = "arraybuffer";
    this.#channel.addEventListener("message", (event: MessageEvent<ArrayBuffer>) => {
      if (event.data instanceof ArrayBuffer) this.frameHandler(new Uint8Array(event.data));
    });
    this.#channel.addEventListener("close", () => this.closeHandler());
    peer.addEventListener("icecandidate", (event) => {
      if (event.candidate) socket.send(JSON.stringify({ type: "candidate", candidate: event.candidate.toJSON() }));
    });
    peer.addEventListener("connectionstatechange", () => {
      if (peer.connectionState === "failed" || peer.connectionState === "disconnected") this.closeHandler();
    });
    await new Promise<void>((resolve, reject) => {
      const abort = (): void => reject(new DOMException("The operation was aborted", "AbortError"));
      socket.addEventListener("open", async () => {
        try {
          const offer = await peer.createOffer();
          await peer.setLocalDescription(offer);
          socket.send(JSON.stringify({ type: "offer", sdp: offer.sdp ?? "" }));
        } catch (error) {
          reject(error);
        }
      }, { once: true });
      this.#channel?.addEventListener("open", () => {
        signal.removeEventListener("abort", abort);
        resolve();
      }, { once: true });
      socket.addEventListener("message", (event) => {
        let message: unknown;
        try {
          message = JSON.parse(String(event.data));
        } catch {
          reject(new Error("Invalid WebRTC signaling JSON"));
          return;
        }
        if (!isSignalMessage(message)) return;
        if (message.type === "answer") {
          void peer.setRemoteDescription({ type: "answer", sdp: message.sdp }).then(async () => {
            for (const candidate of this.#candidates) await peer.addIceCandidate(candidate);
            this.#candidates = [];
          }).catch(reject);
        } else if (message.type === "candidate") {
          if (peer.remoteDescription) void peer.addIceCandidate(message.candidate).catch(reject);
          else this.#candidates.push(message.candidate);
        } else if (message.type === "bye") {
          this.closeHandler();
        }
      });
      socket.addEventListener("error", () => reject(new Error("WebRTC signaling connection failed")), { once: true });
      socket.addEventListener("close", () => this.closeHandler());
      signal.addEventListener("abort", abort, { once: true });
    });
  }

  async send(frame: Uint8Array): Promise<void> {
    if (!this.#channel || this.#channel.readyState !== "open") {
      throw new Error("WebRTC data channel is not connected");
    }
    const copy = new Uint8Array(frame.length);
    copy.set(frame);
    this.#channel.send(copy);
  }

  async close(): Promise<void> {
    if (this.#socket?.readyState === WebSocket.OPEN) this.#socket.send(JSON.stringify({ type: "bye" }));
    this.#channel?.close();
    this.#peer?.close();
    this.#socket?.close();
    this.#channel = null;
    this.#peer = null;
    this.#socket = null;
  }
}
