import { FrameSplitter } from "../codec.ts";
import type { TransportKind } from "../types.ts";

export interface Transport {
  readonly kind: TransportKind;
  open(signal: AbortSignal): Promise<void>;
  send(frame: Uint8Array): Promise<void>;
  close(): Promise<void>;
  onFrame(callback: (frame: Uint8Array) => void): void;
  onClose(callback: () => void): void;
}

export abstract class BaseTransport implements Transport {
  abstract readonly kind: TransportKind;
  protected frameHandler: (frame: Uint8Array) => void = () => undefined;
  protected closeHandler: () => void = () => undefined;
  protected readonly splitter = new FrameSplitter();

  abstract open(signal: AbortSignal): Promise<void>;
  abstract send(frame: Uint8Array): Promise<void>;
  abstract close(): Promise<void>;

  onFrame(callback: (frame: Uint8Array) => void): void {
    this.frameHandler = callback;
  }

  onClose(callback: () => void): void {
    this.closeHandler = callback;
  }

  protected acceptBytes(bytes: Uint8Array): void {
    for (const frame of this.splitter.push(bytes)) this.frameHandler(frame);
  }
}

export function abortError(): DOMException {
  return new DOMException("The operation was aborted", "AbortError");
}

export function rejectIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw abortError();
}
