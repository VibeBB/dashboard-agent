import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import {
  cobsDecode,
  cobsEncode,
  crc16,
} from '../src/codec.ts';

const modulePath = process.argv[2];
if (!modulePath) throw new Error('usage: node wasm-parity.mjs <emcc-module.js>');
const { default: createCodec } = await import(pathToFileURL(modulePath).href);
const codec = await createCodec();

const vectors = [
  new Uint8Array(),
  Uint8Array.from([0]),
  Uint8Array.from([1, 0, 2, 0, 3]),
  new Uint8Array(254).fill(0x5a),
  new Uint8Array(255).fill(0x5a),
  Uint8Array.from({ length: 512 }, (_, index) => index % 256),
];

for (const input of vectors) {
  const capacity = input.length + Math.ceil(input.length / 254) + 2;
  const inputPointer = codec._malloc(Math.max(1, input.length));
  const outputPointer = codec._malloc(capacity);
  const decodePointer = codec._malloc(Math.max(1, input.length + 2));
  try {
    codec.HEAPU8.set(input, inputPointer);
    const encodedLength = codec._dash_cobs_encode(inputPointer, input.length, outputPointer, capacity);
    const wasmEncoded = codec.HEAPU8.slice(outputPointer, outputPointer + encodedLength);
    assert.deepEqual(wasmEncoded, cobsEncode(input));

    codec.HEAPU8.set(wasmEncoded, outputPointer);
    const decodedLength = codec._dash_cobs_decode(outputPointer, encodedLength, decodePointer, input.length + 2);
    assert.deepEqual(codec.HEAPU8.slice(decodePointer, decodePointer + decodedLength), input);
    assert.deepEqual(cobsDecode(wasmEncoded), input);
  } finally {
    codec._free(inputPointer);
    codec._free(outputPointer);
    codec._free(decodePointer);
  }
}

const check = new TextEncoder().encode('123456789');
const checkPointer = codec._malloc(check.length);
try {
  codec.HEAPU8.set(check, checkPointer);
  assert.equal(codec._dash_crc16(checkPointer, check.length), crc16(check));
  assert.equal(codec._dash_crc16(checkPointer, check.length), 0x29b1);
} finally {
  codec._free(checkPointer);
}

console.log('WASM and TypeScript CRC/COBS vectors match');
