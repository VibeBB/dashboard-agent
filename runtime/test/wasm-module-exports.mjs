import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

const modulePath = process.argv[2];
const expectedExports = process.argv.slice(3);
if (!modulePath || expectedExports.length === 0) {
  throw new Error('usage: node wasm-module-exports.mjs <emcc-module.mjs> <export>...');
}

const { default: createModule } = await import(pathToFileURL(modulePath).href);
const module = await createModule();
for (const name of expectedExports) {
  assert.equal(typeof module[`_${name}`], 'function', `missing WASM export: ${name}`);
}

console.log(`WASM exports available: ${expectedExports.join(', ')}`);
