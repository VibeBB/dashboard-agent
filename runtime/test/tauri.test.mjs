import assert from 'node:assert/strict';
import test from 'node:test';
import { filterTauriBleDevices, filterTauriSerialPorts, registerTauriBackends } from '../src/transports/tauri.ts';
import { TauriBleTransport } from '../src/transports/tauri-ble.ts';
import { TauriSerialTransport } from '../src/transports/tauri-serial.ts';

const bleConfig = {
  id: 'native-ble',
  kind: 'tauri_ble',
  service_uuid: '12345678-1234-5678-1234-56789abcdef0',
  rx_characteristic: '12345678-1234-5678-1234-56789abcdef1',
  tx_characteristic: '12345678-1234-5678-1234-56789abcdef2',
  name_prefix: 'Kettle',
};
const serialConfig = {
  id: 'native-serial',
  kind: 'tauri_serial',
  baud_rate: 115200,
  usb_vendor_id: 0x1234,
  usb_product_id: 0x5678,
};

test('native picker filters BLE devices by name and service and serial ports by USB IDs', () => {
  const devices = filterTauriBleDevices([
    { address: 'good', name: 'Kettle One', services: ['12345678-1234-5678-1234-56789abcdef0'] },
    { address: 'wrong-name', name: 'Sensor', services: ['12345678-1234-5678-1234-56789abcdef0'] },
    { address: 'wrong-service', name: 'Kettle Two', services: ['0000180d-0000-1000-8000-00805f9b34fb'] },
  ], bleConfig);
  assert.deepEqual(devices.map((device) => device.address), ['good']);

  const ports = filterTauriSerialPorts({
    good: {
      path: '/dev/ttyUSB0',
      manufacturer: 'Maker',
      pid: '5678',
      product: 'Adapter',
      serial_number: 'A',
      type: 'PCI',
      vid: '0x1234',
    },
    wrongVendor: {
      path: '/dev/ttyUSB1',
      manufacturer: 'Maker',
      pid: '5678',
      product: 'Adapter',
      serial_number: 'B',
      type: 'PCI',
      vid: '4321',
    },
    unknown: {
      path: '/dev/ttyUSB2',
      manufacturer: 'Unknown',
      pid: 'Unknown',
      product: 'Unknown',
      serial_number: 'Unknown',
      type: 'PCI',
      vid: 'Unknown',
    },
  }, serialConfig);
  assert.deepEqual(ports.map((port) => port.path), ['/dev/ttyUSB0']);
});

test('Tauri BLE connects the picked device, splits frames, writes, and disconnects', async () => {
  const chunks = [];
  const writes = [];
  let notify = () => {};
  let disconnected = () => {};
  let unsubscribeCount = 0;
  let disconnectCount = 0;
  const backend = {
    async startScan() {},
    async stopScan() {},
    async connect(address, onDisconnect) {
      assert.equal(address, 'device-1');
      disconnected = onDisconnect;
    },
    async disconnect() {
      disconnectCount += 1;
      disconnected?.();
    },
    async subscribe(characteristic, service, handler) {
      assert.equal(characteristic, bleConfig.rx_characteristic);
      assert.equal(service, bleConfig.service_uuid);
      notify = handler;
    },
    async unsubscribe() { unsubscribeCount += 1; },
    async send(characteristic, data, writeType, service) {
      assert.equal(characteristic, bleConfig.tx_characteristic);
      assert.equal(writeType, 'withResponse');
      assert.equal(service, bleConfig.service_uuid);
      writes.push(data);
    },
  };

  Object.defineProperty(globalThis, '__TAURI_INTERNALS__', { configurable: true, value: {} });
  registerTauriBackends({ ble: backend });
  try {
    const transport = new TauriBleTransport(bleConfig, { address: 'device-1' });
    transport.onFrame((frame) => chunks.push(Array.from(frame)));
    await transport.open(new AbortController().signal);
    notify([2, 49]);
    notify([50, 0]);
    assert.deepEqual(chunks, [[2, 49, 50, 0]]);

    await transport.send(new Uint8Array([7, 8, 0]));
    assert.deepEqual(writes, [[7, 8, 0]]);
    await transport.close();
    assert.equal(unsubscribeCount, 1);
    assert.equal(disconnectCount, 1);
  } finally {
    registerTauriBackends({});
    delete globalThis.__TAURI_INTERNALS__;
  }
});

test('Tauri serial watches byte chunks, writes frames, and closes on disconnect', async () => {
  const received = [];
  const writes = [];
  let handlers;
  let closed = 0;
  let unwatched = 0;
  class FakePort {
    async open() { return 'opened'; }
    async watch(watchHandlers, options) {
      handlers = watchHandlers;
      assert.deepEqual(options, { decode: false });
      return { async unwatch() { unwatched += 1; } };
    }
    async close() { closed += 1; }
    async writeBinary(value) {
      writes.push(Array.from(value));
      return value.length;
    }
  }
  const backend = {
    SerialPort: Object.assign(FakePort, {
      async available_ports() { return {}; },
    }),
  };

  Object.defineProperty(globalThis, '__TAURI_INTERNALS__', { configurable: true, value: {} });
  registerTauriBackends({ serial: backend });
  try {
    const transport = new TauriSerialTransport(
      { id: 'native-serial', kind: 'tauri_serial', baud_rate: 115200 },
      { path: '/dev/ttyUSB0' },
    );
    transport.onFrame((frame) => received.push(Array.from(frame)));
    transport.onClose(() => { handlers = undefined; });
    await transport.open(new AbortController().signal);
    handlers.onData(new Uint8Array([2, 49]));
    handlers.onData(new Uint8Array([50, 0]));
    assert.deepEqual(received, [[2, 49, 50, 0]]);

    await transport.send(new Uint8Array([9, 10, 0]));
    assert.deepEqual(writes, [[9, 10, 0]]);
    handlers.onDisconnect?.('port removed');
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(unwatched, 1);
    assert.equal(closed, 1);
  } finally {
    registerTauriBackends({});
    delete globalThis.__TAURI_INTERNALS__;
  }
});
