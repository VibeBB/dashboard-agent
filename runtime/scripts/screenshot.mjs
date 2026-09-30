import { createServer } from 'node:http';
import { mkdir, readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from '@playwright/test';

const mimeTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.wasm', 'application/wasm'],
  ['.webmanifest', 'application/manifest+json; charset=utf-8'],
  ['.woff', 'font/woff'],
  ['.woff2', 'font/woff2'],
]);

function argumentsFrom(argv) {
  const values = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!['--app', '--out'].includes(key) || index + 1 >= argv.length) {
      throw new Error('usage: screenshot.mjs --app <generated-dir> --out <output-dir>');
    }
    values.set(key, argv[index + 1]);
    index += 1;
  }
  const app = values.get('--app');
  const out = values.get('--out');
  if (!app || !out || values.size !== 2) {
    throw new Error('usage: screenshot.mjs --app <generated-dir> --out <output-dir>');
  }
  return { app: resolve(app), out: resolve(out) };
}

function isContained(path, root) {
  return path === root || path.startsWith(`${root}${sep}`);
}

function createStaticServer(root) {
  return createServer(async (request, response) => {
    let pathname;
    try {
      pathname = decodeURIComponent(
        new URL(request.url ?? '/', 'http://127.0.0.1').pathname,
      );
    } catch {
      response.writeHead(400).end('bad request');
      return;
    }
    const relative = pathname.replace(/^\/+/, '');
    const candidate = resolve(root, relative || 'index.html');
    if (!isContained(candidate, root)) {
      response.writeHead(403).end('forbidden');
      return;
    }
    try {
      const file = await realpath(candidate);
      if (!isContained(file, root) || !(await stat(file)).isFile()) {
        response.writeHead(403).end('forbidden');
        return;
      }
      const extension = file.slice(file.lastIndexOf('.'));
      response.writeHead(200, {
        'cache-control': 'no-store',
        'content-type': mimeTypes.get(extension) ?? 'application/octet-stream',
      }).end(await readFile(file));
    } catch {
      response.writeHead(404).end('not found');
    }
  });
}

async function listen(server) {
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('static server did not bind to a TCP port');
  }
  return `http://127.0.0.1:${address.port}/`;
}

async function main() {
  const { app, out } = argumentsFrom(process.argv.slice(2));
  const root = await realpath(app);
  if (!(await stat(root)).isDirectory()) {
    throw new Error(`generated app is not a directory: ${app}`);
  }
  await mkdir(out, { recursive: true });
  const server = createStaticServer(root);
  let browser;
  try {
    const baseUrl = await listen(server);
    browser = await chromium.launch({ headless: true });
    const viewports = [];
    for (const viewport of [
      { name: 'desktop', width: 1280, height: 800, isMobile: false },
      { name: 'mobile', width: 390, height: 844, isMobile: true },
    ]) {
      const pageErrors = [];
      const consoleErrors = [];
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: 1,
        isMobile: viewport.isMobile,
      });
      const page = await context.newPage();
      page.on('pageerror', (error) => pageErrors.push(error.message));
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text());
      });
      const file = `${viewport.name}.png`;
      try {
        const response = await page.goto(baseUrl, { waitUntil: 'load' });
        if (!response || !response.ok()) {
          throw new Error(`navigation failed with HTTP ${response?.status() ?? 'no response'}`);
        }
        await page.locator('#connection-panel').waitFor({ state: 'visible' });
        await page.screenshot({
          path: resolve(out, file),
          fullPage: true,
          animations: 'disabled',
          caret: 'hide',
        });
      } catch (error) {
        throw new Error(
          `${viewport.name} capture failed: ${error instanceof Error ? error.message : error}`,
        );
      } finally {
        await context.close();
      }
      viewports.push({
        name: viewport.name,
        browser: 'chromium',
        browser_version: browser.version(),
        width: viewport.width,
        height: viewport.height,
        file,
        page_errors: pageErrors,
        console_errors: consoleErrors,
      });
    }
    await writeFile(
      resolve(out, 'screens.json'),
      `${JSON.stringify(
        {
          browser: 'chromium',
          browser_version: browser.version(),
          viewports,
        },
        null,
        2,
      )}\n`,
    );
  } finally {
    if (browser) await browser.close();
    await new Promise((resolveClose) => server.close(resolveClose));
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
