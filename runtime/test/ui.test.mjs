import assert from 'node:assert/strict';
import test from 'node:test';
import {
  describeFault,
  formatFieldLabel,
  formatFieldValue,
  pickLocale,
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

test('fault readouts decode codes through the pinned fault table', () => {
  const faults = [{ code: 2, name: 'scale', severity: 'warning', action: 'Descale the kettle' }];
  assert.equal(describeFault(0, faults), 'No fault');
  assert.equal(describeFault(2, faults), 'scale (warning): Descale the kettle');
  assert.equal(describeFault(3, faults), 'Unknown fault code 3');
  assert.equal(describeFault(-1, faults), 'Invalid fault code -1');
  assert.equal(describeFault(true, faults), 'Invalid fault code true');
  const output = { value: '', dataset: { message: 'status', field: 'error_code', fault: '' }, parentElement: null };
  renderTelemetry({ querySelectorAll: () => [output] }, { status: { error_code: 2 } }, faults);
  assert.equal(output.value, 'scale (warning): Descale the kettle');
});

test('locale choice prefers exact tags, then the primary language, then the default', () => {
  assert.equal(pickLocale('en', ['ja', 'de-CH'], ['ja-JP', 'en']), 'ja');
  assert.equal(pickLocale('en', ['ja', 'de-CH'], ['de-CH']), 'de-CH');
  assert.equal(pickLocale('en', ['ja', 'de-CH'], ['de-AT']), 'de-CH');
  assert.equal(pickLocale('en', ['ja'], ['en-GB', 'ja']), 'en');
  assert.equal(pickLocale('en', ['ja'], ['fr']), 'en');
  assert.equal(pickLocale('en', ['ja'], []), 'en');
});
