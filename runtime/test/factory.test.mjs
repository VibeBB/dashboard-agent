import assert from 'node:assert/strict';
import test from 'node:test';
import { fillTemplate, LineBuffer, lineIo, placeholders, runFactory } from '../src/factory.ts';

const commands = [
  { id: 'TC-01', name: 'sensors', request: 'TEST SENSORS', response_pattern: 'SENSORS PASS', timeout_ms: 50, destructive: false },
  { id: 'TC-02', name: 'provision', request: 'PROVISION <serial>', response_pattern: 'PROVISIONED <serial>', timeout_ms: 50, destructive: true },
];

function fakeIo(replies) {
  const sent = [];
  return {
    sent,
    send: async (line) => { sent.push(line); },
    nextLine: async () => replies.shift() ?? null,
  };
}

test('placeholders are collected once and filled from operator values', () => {
  assert.deepEqual(placeholders(commands), ['serial']);
  assert.equal(fillTemplate('PROVISION <serial>', { serial: ' SN1 ' }), 'PROVISION SN1');
  assert.throws(() => fillTemplate('PROVISION <serial>', {}), /missing/);
  assert.throws(() => fillTemplate('PROVISION <serial>', { serial: 'A\nB' }), /multi-line/);
});

test('line buffer splits CRLF and keeps partial lines', () => {
  const buffer = new LineBuffer();
  const encode = (text) => new TextEncoder().encode(text);
  assert.deepEqual(buffer.push(encode('SENSORS ')), []);
  assert.deepEqual(buffer.push(encode('PASS\r\nPROV')), ['SENSORS PASS']);
  assert.deepEqual(buffer.push(encode('ISIONED\n')), ['PROVISIONED']);
});

test('all steps pass when every reply matches', async () => {
  const io = fakeIo(['boot noise', 'SENSORS PASS', 'PROVISIONED SN1']);
  const results = await runFactory(io, commands, { serial: 'SN1' }, () => true);
  assert.deepEqual(results.map((item) => item.status), ['pass', 'pass']);
  assert.deepEqual(io.sent, ['TEST SENSORS\n', 'PROVISION SN1\n']);
});

test('a wrong reply, a timeout or a cancelled destructive step stops the run', async () => {
  const wrong = await runFactory(fakeIo(['SENSORS FAIL']), commands, { serial: 'SN1' }, () => true, () => 0);
  assert.equal(wrong.length, 1);
  assert.equal(wrong[0].status, 'fail');
  const silent = await runFactory(fakeIo([]), commands, { serial: 'SN1' }, () => true);
  assert.deepEqual(silent, [{ id: 'TC-01', status: 'fail', line: 'timeout' }]);
  const io = fakeIo(['SENSORS PASS']);
  const cancelled = await runFactory(io, commands, { serial: 'SN1' }, () => false);
  assert.equal(cancelled[1].line, 'cancelled by operator');
  assert.deepEqual(io.sent, ['TEST SENSORS\n']);
  let clock = 0;
  const late = await runFactory(
    { send: async () => undefined, nextLine: async () => { clock += 60; return 'noise'; } },
    commands, { serial: 'SN1' }, () => true, () => clock,
  );
  assert.deepEqual(late, [{ id: 'TC-01', status: 'fail', line: 'noise' }]);
});

test('line io queues bytes from the transport and times out when silent', async () => {
  let push = () => undefined;
  const written = [];
  const io = lineIo({ send: async (bytes) => { written.push(new TextDecoder().decode(bytes)); }, onBytes: (callback) => { push = callback; } });
  push(new TextEncoder().encode('A\n'));
  assert.equal(await io.nextLine(10), 'A');
  const waiting = io.nextLine(1000);
  push(new TextEncoder().encode('B\n'));
  assert.equal(await waiting, 'B');
  assert.equal(await io.nextLine(5), null);
  await io.send('X\n');
  assert.deepEqual(written, ['X\n']);
  assert.throws(() => lineIo({ send: async () => undefined }), /raw bytes/);
});
