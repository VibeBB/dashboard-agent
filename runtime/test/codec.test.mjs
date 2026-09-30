import assert from 'node:assert/strict';
import test from 'node:test';
import {
  cobsDecode,
  cobsEncode,
  crc16,
  decodeFrame,
  encodeAck,
  encodeMessage,
  FrameSplitter,
} from '../src/codec.ts';

test('CRC-16/CCITT-FALSE uses the standard check vector', () => {
  assert.equal(crc16(new TextEncoder().encode('123456789')), 0x29b1);
});

test('COBS round trips empty, zero-containing, and 254/255-byte runs', () => {
  for (const value of [
    new Uint8Array(),
    Uint8Array.from([0]),
    Uint8Array.from([0, 1, 0, 2, 0]),
    new Uint8Array(254).fill(0x7a),
    new Uint8Array(255).fill(0x7a),
    Uint8Array.from({ length: 512 }, (_, index) => index % 256),
  ]) {
    assert.deepEqual(cobsDecode(cobsEncode(value)), value);
  }
  assert.equal(cobsEncode(new Uint8Array(254).fill(1)).length, 256);
  assert.equal(cobsEncode(new Uint8Array(255).fill(1)).length, 257);
});

test('message frames round trip scaled fields with CRC and sequence', () => {
  const message = {
    id: 1,
    name: 'telemetry',
    direction: 'device_to_host',
    ack: false,
    fields: [
      { name: 'temperature', type: 'i16', scale: 0.1, min: -40, max: 120 },
      { name: 'enabled', type: 'bool', scale: 1 },
    ],
  };
  const frame = encodeMessage(message, { temperature: 23.4, enabled: true }, 19);
  assert.equal(frame.at(-1), 0);
  assert.deepEqual(decodeFrame(frame, [message]), {
    id: 1,
    seq: 19,
    name: 'telemetry',
    values: { temperature: 23.400000000000002, enabled: true },
  });
  const corrupted = frame.slice();
  corrupted[1] ^= 1;
  assert.throws(() => decodeFrame(corrupted, [message]), /CRC16 mismatch/);
});

test('ACK frames carry command id, sequence, and status', () => {
  const decoded = decodeFrame(encodeAck(4, 22, 0, 9), []);
  assert.deepEqual(decoded.ack, { id: 4, seq: 22, status: 0 });
});

test('frame splitter preserves partial frames and separates coalesced frames', () => {
  const splitter = new FrameSplitter();
  const first = Uint8Array.from([1, 2, 0]);
  const second = Uint8Array.from([3, 0]);
  assert.deepEqual(splitter.push(first.slice(0, 2)), []);
  assert.deepEqual(splitter.push(Uint8Array.from([...first.slice(2), ...second])), [first, second]);
});
