import type { FieldConfig, MessageConfig, WireType } from "./types.ts";

const WIDTHS: Record<WireType, number> = {
  u8: 1,
  i8: 1,
  u16: 2,
  i16: 2,
  u32: 4,
  i32: 4,
  f32: 4,
  bool: 1,
};
const WIRE_LIMITS: Record<WireType, readonly [number, number]> = {
  u8: [0, 0xff],
  i8: [-0x80, 0x7f],
  u16: [0, 0xffff],
  i16: [-0x8000, 0x7fff],
  u32: [0, 0xffffffff],
  i32: [-0x80000000, 0x7fffffff],
  f32: [-3.4028235e38, 3.4028235e38],
  bool: [0, 1],
};

export interface DecodedMessage {
  id: number;
  seq: number;
  name?: string;
  values?: Record<string, number | boolean>;
  ack?: { id: number; seq: number; status: number };
}

export class FrameSplitter {
  #pending: number[] = [];

  push(chunk: Uint8Array): Uint8Array[] {
    const frames: Uint8Array[] = [];
    for (const byte of chunk) {
      if (byte === 0) {
        if (this.#pending.length) {
          frames.push(Uint8Array.from([...this.#pending, 0]));
          this.#pending = [];
        }
      } else {
        this.#pending.push(byte);
      }
    }
    return frames;
  }
}

export function crc16(bytes: Uint8Array): number {
  let crc = 0xffff;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 0x8000) !== 0 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc;
}

export function cobsEncode(input: Uint8Array): Uint8Array {
  const output = new Uint8Array(input.length + Math.ceil(input.length / 254) + 1);
  let read = 0;
  let write = 1;
  let codeIndex = 0;
  let code = 1;
  while (read < input.length) {
    if (input[read] === 0) {
      output[codeIndex] = code;
      codeIndex = write;
      write += 1;
      code = 1;
    } else {
      output[write] = input[read];
      write += 1;
      code += 1;
      if (code === 0xff) {
        output[codeIndex] = code;
        codeIndex = write;
        write += 1;
        code = 1;
      }
    }
    read += 1;
  }
  output[codeIndex] = code;
  return output.slice(0, write);
}

export function cobsDecode(input: Uint8Array): Uint8Array {
  const encoded = input.at(-1) === 0 ? input.subarray(0, input.length - 1) : input;
  const output: number[] = [];
  let cursor = 0;
  while (cursor < encoded.length) {
    const code = encoded[cursor];
    if (code === undefined || code === 0) throw new Error("Invalid COBS frame");
    cursor += 1;
    const end = cursor + code - 1;
    if (end > encoded.length) throw new Error("Truncated COBS block");
    for (; cursor < end; cursor += 1) {
      const value = encoded[cursor];
      if (value === undefined) throw new Error("Truncated COBS block");
      output.push(value);
    }
    if (code < 0xff && cursor < encoded.length) output.push(0);
  }
  return Uint8Array.from(output);
}

function writeField(view: DataView, offset: number, field: FieldConfig, value: number | boolean): void {
  if (field.type === "bool") {
    if (typeof value !== "boolean") throw new TypeError(`${field.name} must be a boolean`);
    view.setUint8(offset, value ? 1 : 0);
    return;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`${field.name} must be a finite number`);
  }
  const wire = field.type === "f32" ? value / field.scale : Math.round(value / field.scale);
  if (field.min !== undefined && field.min !== null && value < field.min) {
    throw new RangeError(`${field.name} is below its minimum`);
  }
  if (field.max !== undefined && field.max !== null && value > field.max) {
    throw new RangeError(`${field.name} is above its maximum`);
  }
  const [wireMin, wireMax] = WIRE_LIMITS[field.type];
  if (wire < wireMin || wire > wireMax) throw new RangeError(`${field.name} is outside its wire type range`);
  switch (field.type) {
    case "u8": view.setUint8(offset, wire); break;
    case "i8": view.setInt8(offset, wire); break;
    case "u16": view.setUint16(offset, wire, true); break;
    case "i16": view.setInt16(offset, wire, true); break;
    case "u32": view.setUint32(offset, wire, true); break;
    case "i32": view.setInt32(offset, wire, true); break;
    case "f32": view.setFloat32(offset, wire, true); break;
  }
}

function readField(view: DataView, offset: number, field: FieldConfig): number | boolean {
  if (field.type === "bool") return view.getUint8(offset) !== 0;
  let value: number;
  switch (field.type) {
    case "u8": value = view.getUint8(offset); break;
    case "i8": value = view.getInt8(offset); break;
    case "u16": value = view.getUint16(offset, true); break;
    case "i16": value = view.getInt16(offset, true); break;
    case "u32": value = view.getUint32(offset, true); break;
    case "i32": value = view.getInt32(offset, true); break;
    case "f32": value = view.getFloat32(offset, true); break;
  }
  return value * field.scale;
}

export function encodeMessage(
  message: MessageConfig,
  values: Record<string, number | boolean>,
  seq: number,
): Uint8Array {
  const payloadBytes = message.fields.reduce((size, field) => size + WIDTHS[field.type], 0);
  const raw = new Uint8Array(2 + payloadBytes + 2);
  const view = new DataView(raw.buffer);
  view.setUint8(0, message.id);
  view.setUint8(1, seq & 0xff);
  let offset = 2;
  for (const field of message.fields) {
    const value = values[field.name];
    if (value === undefined) throw new TypeError(`missing field ${field.name}`);
    writeField(view, offset, field, value);
    offset += WIDTHS[field.type];
  }
  view.setUint16(offset, crc16(raw.subarray(0, offset)), true);
  const encoded = cobsEncode(raw);
  const frame = new Uint8Array(encoded.length + 1);
  frame.set(encoded);
  return frame;
}

export function decodeFrame(
  frame: Uint8Array,
  messages: MessageConfig[],
  maxFrameBytes = Number.POSITIVE_INFINITY,
): DecodedMessage {
  if (frame.byteLength > maxFrameBytes) throw new Error("Frame exceeds configured maximum size");
  const raw = cobsDecode(frame);
  if (raw.length < 4) throw new Error("Frame is too short");
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const expected = view.getUint16(raw.length - 2, true);
  if (crc16(raw.subarray(0, raw.length - 2)) !== expected) throw new Error("CRC16 mismatch");
  const id = view.getUint8(0);
  const seq = view.getUint8(1);
  if (id === 0xff) {
    if (raw.length !== 7) throw new Error("Invalid ACK frame");
    return { id, seq, ack: { id: view.getUint8(2), seq: view.getUint8(3), status: view.getUint8(4) } };
  }
  const message = messages.find((candidate) => candidate.id === id);
  if (!message) throw new Error(`Unknown message id ${id}`);
  const values: Record<string, number | boolean> = {};
  let offset = 2;
  for (const field of message.fields) {
    if (offset + WIDTHS[field.type] > raw.length - 2) throw new Error("Truncated message payload");
    values[field.name] = readField(view, offset, field);
    offset += WIDTHS[field.type];
  }
  if (offset !== raw.length - 2) throw new Error("Unexpected message payload");
  return { id, seq, name: message.name, values };
}

export function encodeAck(ackedId: number, ackedSeq: number, status: number, seq: number): Uint8Array {
  const raw = new Uint8Array([0xff, seq & 0xff, ackedId, ackedSeq, status, 0, 0]);
  const checksum = crc16(raw.subarray(0, 5));
  raw[5] = checksum & 0xff;
  raw[6] = checksum >> 8;
  const encoded = cobsEncode(raw);
  const frame = new Uint8Array(encoded.length + 1);
  frame.set(encoded);
  return frame;
}
