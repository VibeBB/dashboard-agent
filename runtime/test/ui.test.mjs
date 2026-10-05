import assert from 'node:assert/strict';
import test from 'node:test';
import {
  formatFieldLabel,
  formatFieldValue,
  renderTelemetry,
} from '../src/ui.ts';

test('field labels and values retain human-readable units', () => {
  assert.equal(formatFieldLabel('target_temp_c', '°C'), 'target temp c (°C)');
  assert.equal(formatFieldLabel('heating'), 'heating');
  assert.equal(formatFieldValue(23.5, '°C'), '23.5 °C');
  assert.equal(formatFieldValue(false), 'Off');
});

test('telemetry readouts append units for values, gauges, and charts', () => {
  const meter = { min: 0, max: 100, value: 0 };
  const context = {
    clearRect() {},
    beginPath() {},
    moveTo() {},
    lineTo() {},
    stroke() {},
  };
  const canvas = {
    width: 600,
    height: 160,
    getContext: () => context,
  };
  const outputs = ['value', 'gauge', 'chart'].map((kind) => ({
    dataset: { message: 'status', field: 'water_temp_c', unit: '°C', history: '[]' },
    value: '—',
    parentElement: {
      querySelector(selector) {
        if (kind === 'gauge' && selector === 'meter') return meter;
        if (kind === 'chart' && selector === 'canvas') return canvas;
        return null;
      },
    },
  }));
  const root = { querySelectorAll: () => outputs };

  renderTelemetry(root, { status: { water_temp_c: 23.5 } });

  assert.deepEqual(outputs.map((output) => output.value), [
    '23.5 °C',
    '23.5 °C',
    '23.5 °C',
  ]);
  assert.equal(meter.value, 23.5);
  assert.equal(outputs[2].dataset.history, '[23.5]');
});
