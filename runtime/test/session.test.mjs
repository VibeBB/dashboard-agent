import assert from 'node:assert/strict';
import test from 'node:test';
import { encodeAck, encodeMessage } from '../src/codec.ts';
import { DashboardSession } from '../src/session.ts';

const telemetry = {
  id: 1,
  name: 'telemetry',
  direction: 'device_to_host',
  ack: false,
  fields: [{ name: 'temperature', type: 'i16', scale: 0.1, min: -40, max: 120 }],
};
const setTarget = {
  id: 2,
  name: 'set_target',
  direction: 'host_to_device',
  ack: true,
  fields: [{ name: 'temperature', type: 'u16', scale: 0.1, min: 30, max: 100 }],
};
const config = {
  contract_sha256: 'abc',
  contract: {
    name: 'smart-kettle',
    description: 'Kettle',
    protocol: { max_frame_bytes: 32, messages: [telemetry, setTarget] },
    transports: [{ id: 'serial', kind: 'web_serial', baud_rate: 115200 }],
    platforms: [],
    widgets: [],
    session: { connect_timeout_ms: 1000, ack_timeout_ms: 1000, reconnect: { max_attempts: 1, backoff_ms: 0 } },
  },
  routes: [],
  webmcp_tools: [],
};

class FakeTransport {
  frames = [];
  opened = false;
  frameHandler = () => {};
  closeHandler = () => {};
  async open() { this.opened = true; }
  async send(frame) { this.frames.push(frame); }
  async close() { this.opened = false; }
  onFrame(callback) { this.frameHandler = callback; }
  onClose(callback) { this.closeHandler = callback; }
  receive(frame) { this.frameHandler(frame); }
  disconnect() { this.closeHandler(); }
}

test('commands fail closed when disconnected and wait for matching ACK', async () => {
  const transports = [];
  const session = new DashboardSession(config, {
    createTransport: () => {
      const transport = new FakeTransport();
      transports.push(transport);
      return transport;
    },
  });
  await assert.rejects(session.sendCommand('set_target', { temperature: 60 }), /disconnected/);
  await session.connect(config.contract.transports[0]);
  const command = session.sendCommand('set_target', { temperature: 60 });
  assert.equal(transports[0].frames.length, 1);
  transports[0].receive(encodeAck(setTarget.id, 0, 0, 1));
  assert.deepEqual(await command, { sent: true, acked: true, seq: 0 });
});

test('ACK timeout fails the command and mismatched ACK identifiers are rejected', async () => {
  const shortTimeout = {
    ...config,
    contract: {
      ...config.contract,
      session: { ...config.contract.session, ack_timeout_ms: 10 },
    },
  };
  const transport = new FakeTransport();
  const session = new DashboardSession(shortTimeout, { createTransport: () => transport });
  await session.connect(config.contract.transports[0]);
  await assert.rejects(session.sendCommand('set_target', { temperature: 60 }), /ACK timeout/);

  const command = session.sendCommand('set_target', { temperature: 60 });
  transport.receive(encodeAck(99, 1, 0, 2));
  await assert.rejects(command, /message id does not match/);
});

test('hazard commands require confirmation and telemetry is retained', async () => {
  const transport = new FakeTransport();
  const session = new DashboardSession(config, { createTransport: () => transport });
  await session.connect(config.contract.transports[0]);
  await assert.rejects(
    session.sendCommand('set_target', { temperature: 60 }, { hazard: true, confirm: () => false }),
    /cancelled/,
  );
  const frame = encodeMessage(telemetry, { temperature: 42.1 }, 7);
  transport.receive(frame);
  assert.deepEqual(session.telemetry.telemetry, { temperature: 42.1 });
  assert.ok(session.lastSeen.telemetry > 0);
});

test('unexpected transport closure reconnects with configured backoff', async () => {
  const transports = [];
  const session = new DashboardSession(config, {
    createTransport: () => {
      const transport = new FakeTransport();
      transports.push(transport);
      return transport;
    },
    sleep: async () => {},
  });
  await session.connect(config.contract.transports[0]);
  transports[0].disconnect();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(transports.length, 2);
  assert.equal(session.state, 'connected');
});
