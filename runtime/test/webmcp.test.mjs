import assert from 'node:assert/strict';
import test from 'node:test';
import { registerWebMcp } from '../src/webmcp.ts';
import { DashboardSession } from '../src/session.ts';
import { encodeAck } from '../src/codec.ts';

const command = {
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
    protocol: { max_frame_bytes: 32, messages: [command] },
    transports: [{ id: 'serial', kind: 'web_serial', baud_rate: 115200 }],
    platforms: [],
    widgets: [{ command: 'set_target', hazard: true }],
    session: { connect_timeout_ms: 1000, ack_timeout_ms: 1000, reconnect: { max_attempts: 0, backoff_ms: 0 } },
    webmcp: { enabled: true, expose_controls: true },
  },
  routes: [],
  webmcp_tools: [
    {
      name: 'dashboard_status',
      description: 'Status',
      inputSchema: { type: 'object', properties: {} },
      annotations: { readOnlyHint: true },
    },
    {
      name: 'read_telemetry',
      description: 'Read telemetry',
      inputSchema: { type: 'object', properties: {} },
      annotations: { readOnlyHint: true, untrustedContentHint: true },
    },
    {
      name: 'send_set_target',
      description: 'Set target',
      inputSchema: { type: 'object', properties: { temperature: { type: 'number' } } },
      annotations: { consequentialHint: true },
    },
  ],
};

class FakeTransport {
  frameHandler = () => {};
  closeHandler = () => {};
  async open() {}
  async send() {}
  async close() {}
  onFrame(callback) { this.frameHandler = callback; }
  onClose(callback) { this.closeHandler = callback; }
}

test('WebMCP registers only configured tools on document.modelContext and aborts together', async () => {
  const registrations = [];
  globalThis.document = {
    modelContext: {
      registerTool: async (tool, options) => registrations.push({ tool, signal: options.signal }),
    },
  };
  const session = new DashboardSession(config, { createTransport: () => new FakeTransport() });
  const unregister = await registerWebMcp(config, session, () => ({ state: session.state }));
  assert.deepEqual(registrations.map(({ tool }) => tool.name), [
    'dashboard_status',
    'read_telemetry',
    'send_set_target',
  ]);
  assert.ok(registrations.every(({ signal }) => signal === registrations[0].signal));
  assert.equal(registrations[0].signal.aborted, false);
  unregister();
  assert.equal(registrations[0].signal.aborted, true);
  delete globalThis.document;
});

test('WebMCP control tools fail closed, confirm hazards, and wait for ACK', async () => {
  const transport = new FakeTransport();
  globalThis.document = {
    modelContext: {
      registerTool: async (tool) => {
        toolRegistry.set(tool.name, tool);
      },
    },
  };
  globalThis.window = { confirm: () => true };
  const toolRegistry = new Map();
  const session = new DashboardSession(config, { createTransport: () => transport });
  const unregister = await registerWebMcp(config, session, () => ({ state: session.state }));
  await assert.rejects(toolRegistry.get('send_set_target').execute({ temperature: 55 }), /disconnected/);
  await session.connect(config.contract.transports[0]);
  const resultPromise = toolRegistry.get('send_set_target').execute({ temperature: 55 });
  transport.frameHandler(encodeAck(command.id, 0, 0, 1));
  assert.deepEqual(await resultPromise, { sent: true, acked: true, seq: 0 });
  unregister();
  delete globalThis.document;
  delete globalThis.window;
});
