import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

const modulePath = process.argv[2];
if (!modulePath) throw new Error('usage: node wasm-mruby-run.mjs <emcc-module.mjs>');

const { default: createModule } = await import(pathToFileURL(modulePath).href);
const module = await createModule();
assert.equal(typeof module._mruby_ux_init, 'function', 'missing export: mruby_ux_init');
assert.equal(typeof module._mruby_ux_run, 'function', 'missing export: mruby_ux_run');

assert.equal(await module._mruby_ux_init(), 0, 'mruby_ux_init failed');
assert.equal(await module._mruby_ux_run(), 0, 'mruby_ux_run failed');
console.log('mruby/c UX module ran to completion');
