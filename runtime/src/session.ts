import { decodeFrame, encodeAck, encodeMessage, type DecodedMessage } from "./codec.ts";
import type {
  DashboardConfig,
  MessageConfig,
  TelemetryValues,
  TransportConfig,
} from "./types.ts";
import { createTransport } from "./transports/index.ts";
import type { Transport } from "./transports/transport.ts";

export type SessionState = "idle" | "connecting" | "connected" | "reconnecting" | "failed";

interface PendingAck {
  id: number;
  resolve: (value: { sent: true; acked: true; seq: number }) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
}

export interface SessionStatus {
  state: SessionState;
  design: string;
  platform: string;
  platform_status: string;
  platform_reason: string | null;
  usable_routes: string[];
  unavailable_routes: string[];
  caveats: string[];
  capabilities: Record<string, boolean>;
}

export interface SessionOptions {
  createTransport?: (config: TransportConfig) => Transport;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("The operation was aborted", "AbortError"));
    }, { once: true });
  });
}

function asObject(value: unknown): Record<string, number | boolean> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError("Command arguments must be an object");
  }
  const result: Record<string, number | boolean> = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item !== "number" && typeof item !== "boolean") {
      throw new TypeError(`Command field ${key} must be a number or boolean`);
    }
    result[key] = item;
  }
  return result;
}

export class DashboardSession extends EventTarget {
  readonly config: DashboardConfig;
  #state: SessionState = "idle";
  #transport: Transport | null = null;
  #transportConfig: TransportConfig | null = null;
  #controller: AbortController | null = null;
  #seq = 0;
  #pendingAcks = new Map<number, PendingAck>();
  #telemetry: TelemetryValues = {};
  #lastSeen: Record<string, number> = {};
  #reconnecting = false;
  readonly #createTransport: (config: TransportConfig) => Transport;
  readonly #sleep: (ms: number, signal: AbortSignal) => Promise<void>;

  constructor(config: DashboardConfig, options: SessionOptions = {}) {
    super();
    this.config = config;
    this.#createTransport = options.createTransport ?? createTransport;
    this.#sleep = options.sleep ?? sleep;
  }

  get state(): SessionState {
    return this.#state;
  }

  get telemetry(): TelemetryValues {
    return structuredClone(this.#telemetry);
  }

  get lastSeen(): Record<string, number> {
    return { ...this.#lastSeen };
  }

  getStatus(capabilities: Record<string, boolean>, platformName = navigator.platform): SessionStatus {
    const platform = this.config.contract.platforms.find((item) => item.os === platformName);
    const routes = this.config.routes.filter((route) => route.os === platform?.os);
    return {
      state: this.#state,
      design: this.config.contract.name,
      platform: platform?.os ?? platformName,
      platform_status: platform?.status ?? "undeclared",
      platform_reason: platform?.reason ?? null,
      usable_routes: routes.filter((route) => route.support !== "no" && capabilities[route.kind]).map((route) => route.transport),
      unavailable_routes: routes.filter((route) => route.support === "no" || !capabilities[route.kind]).map((route) => route.transport),
      caveats: [...new Set(routes.flatMap((route) => route.caveats))],
      capabilities,
    };
  }

  async connect(transportConfig: TransportConfig): Promise<void> {
    await this.close();
    this.#transportConfig = transportConfig;
    this.#controller = new AbortController();
    this.#state = "connecting";
    this.#emitState();
    const transport = this.#createTransport(transportConfig);
    this.#wire(transport);
    this.#transport = transport;
    const timeout = this.config.contract.session.connect_timeout_ms;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        transport.open(this.#controller.signal),
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error("Connection timed out")), timeout);
        }),
      ]);
      if (this.#controller.signal.aborted) throw new DOMException("The operation was aborted", "AbortError");
      if (timer) clearTimeout(timer);
      this.#state = "connected";
      this.#emitState();
    } catch (error) {
      if (timer) clearTimeout(timer);
      await transport.close();
      this.#transport = null;
      this.#state = "failed";
      this.#emitState();
      throw error;
    }
  }

  #wire(transport: Transport): void {
    transport.onFrame((frame) => this.#receive(frame));
    transport.onClose(() => {
      if (this.#transport === transport && this.#state === "connected" && this.#controller) {
        void this.#reconnect();
      }
    });
  }

  #receive(frame: Uint8Array): void {
    let decoded: DecodedMessage;
    try {
      decoded = decodeFrame(
        frame,
        this.config.contract.protocol.messages,
        this.config.contract.protocol.max_frame_bytes,
      );
    } catch (error) {
      this.dispatchEvent(new CustomEvent("protocolerror", { detail: error }));
      return;
    }
    if (decoded.ack) {
      const pending = this.#pendingAcks.get(decoded.ack.seq);
      if (pending) {
        clearTimeout(pending.timeout);
        this.#pendingAcks.delete(decoded.ack.seq);
        if (decoded.ack.id !== pending.id) {
          pending.reject(new Error("ACK message id does not match the pending command"));
        } else if (decoded.ack.status === 0) {
          pending.resolve({ sent: true, acked: true, seq: decoded.ack.seq });
        } else {
          pending.reject(new Error(`Device rejected command with ACK status ${decoded.ack.status}`));
        }
      }
      return;
    }
    if (!decoded.name || !decoded.values) return;
    this.#telemetry[decoded.name] = decoded.values;
    this.#lastSeen[decoded.name] = Date.now();
    this.dispatchEvent(new CustomEvent("telemetry", { detail: { message: decoded.name, values: decoded.values } }));
  }

  async sendCommand(
    messageName: string,
    input: unknown,
    options: { hazard?: boolean; confirm?: () => boolean; requireConnected?: boolean } = {},
  ): Promise<{ sent: true; acked: boolean; seq: number }> {
    if (this.#state !== "connected" || !this.#transport) throw new Error("Dashboard is disconnected; connect before sending commands");
    const message = this.config.contract.protocol.messages.find(
      (candidate) => candidate.name === messageName && candidate.direction === "host_to_device",
    );
    if (!message) throw new Error(`Unknown host-to-device command: ${messageName}`);
    const values = asObject(input);
    const fieldNames = new Set(message.fields.map((field) => field.name));
    const extraFields = Object.keys(values).filter((name) => !fieldNames.has(name));
    if (extraFields.length) throw new TypeError(`Unknown command fields: ${extraFields.join(", ")}`);
    if (options.hazard) {
      const confirm = options.confirm ?? (() => window.confirm(`Confirm ${messageName}?`));
      if (!confirm()) throw new Error("Command cancelled by user");
    }
    const seq = this.#seq;
    this.#seq = (this.#seq + 1) & 0xff;
    const frame = encodeMessage(message, values, seq);
    if (!message.ack) {
      await this.#transport.send(frame);
      return { sent: true, acked: false, seq };
    }
    const ack = new Promise<{ sent: true; acked: true; seq: number }>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.#pendingAcks.delete(seq);
        reject(new Error(`ACK timeout for ${messageName}`));
      }, this.config.contract.session.ack_timeout_ms);
      this.#pendingAcks.set(seq, { id: message.id, resolve, reject, timeout });
    });
    try {
      await this.#transport.send(frame);
      return await ack;
    } catch (error) {
      const pending = this.#pendingAcks.get(seq);
      if (pending) clearTimeout(pending.timeout);
      this.#pendingAcks.delete(seq);
      throw error;
    }
  }

  createAckFrame(ackedId: number, ackedSeq: number, status = 0): Uint8Array {
    const seq = this.#seq;
    this.#seq = (this.#seq + 1) & 0xff;
    return encodeAck(ackedId, ackedSeq, status, seq);
  }

  async close(): Promise<void> {
    this.#controller?.abort();
    this.#controller = null;
    const current = this.#transport;
    this.#transport = null;
    await current?.close();
    for (const pending of this.#pendingAcks.values()) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("Dashboard disconnected before ACK"));
    }
    this.#pendingAcks.clear();
    this.#state = "idle";
    this.#emitState();
  }

  #emitState(): void {
    this.dispatchEvent(new CustomEvent("statechange", { detail: this.#state }));
  }

  async #reconnect(): Promise<void> {
    if (this.#reconnecting || !this.#transportConfig || !this.#controller) return;
    this.#reconnecting = true;
    this.#state = "reconnecting";
    this.#emitState();
    const { max_attempts: maxAttempts, backoff_ms: backoff } = this.config.contract.session.reconnect;
    for (let attempt = 0; attempt < maxAttempts && this.#controller && !this.#controller.signal.aborted; attempt += 1) {
      try {
        await this.#sleep(backoff * (attempt + 1), this.#controller.signal);
        const next = this.#createTransport(this.#transportConfig);
        this.#wire(next);
        this.#transport = next;
        await next.open(this.#controller.signal);
        this.#state = "connected";
        this.#reconnecting = false;
        this.#emitState();
        return;
      } catch {
        if (this.#transport) await this.#transport.close().catch(() => undefined);
        this.#transport = null;
      }
    }
    this.#state = this.#controller?.signal.aborted ? "idle" : "failed";
    this.#reconnecting = false;
    this.#emitState();
  }
}

export function messageByName(messages: MessageConfig[], name: string): MessageConfig | undefined {
  return messages.find((message) => message.name === name);
}
