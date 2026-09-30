import assert from 'node:assert/strict';
import test from 'node:test';
import { detectEnvironment, selectRoutes } from '../src/capabilities.ts';

test('platform and browser detection distinguishes iOS, iPadOS, and macOS', () => {
  const iphone = detectEnvironment({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
    maxTouchPoints: 5,
    userAgentData: { platform: 'iOS', brands: [] },
  }, true);
  assert.equal(iphone.os, 'ios');
  assert.equal(iphone.browser, 'safari');

  const legacyIpad = detectEnvironment({
    userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
    maxTouchPoints: 5,
  }, true);
  assert.equal(legacyIpad.os, 'ipados');

  const desktopModeIpad = detectEnvironment({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15',
    maxTouchPoints: 5,
    userAgentData: { platform: 'macOS', brands: [] },
  }, true);
  assert.equal(desktopModeIpad.os, 'ipados');
  assert.equal(desktopModeIpad.browser, 'safari');

  const mac = detectEnvironment({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15',
    maxTouchPoints: 0,
    userAgentData: { platform: 'macOS', brands: [] },
  }, true);
  assert.equal(mac.os, 'macos');

  const bluefyIpad = detectEnvironment({
    userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Bluefy/3.0 Safari/604.1',
    maxTouchPoints: 5,
    userAgentData: { platform: 'iOS', brands: [] },
    bluetooth: {},
  }, true);
  assert.equal(bluefyIpad.os, 'ipados');
  assert.equal(bluefyIpad.browser, 'bluefy');
  assert.equal(bluefyIpad.capabilities.web_bluetooth, true);

  const bluefyFallback = detectEnvironment({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
    maxTouchPoints: 5,
    userAgentData: { platform: 'iOS', brands: [] },
    bluetooth: {},
  }, true);
  assert.equal(bluefyFallback.browser, 'bluefy');
});

test('userAgentData.platform takes precedence over conflicting desktop user agents', () => {
  const environment = detectEnvironment({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
    maxTouchPoints: 0,
    userAgentData: { platform: 'Windows', brands: [{ brand: 'Google Chrome' }] },
  }, true);

  assert.equal(environment.os, 'windows');
});

test('BSD operating systems are detected from their user-agent tokens', () => {
  for (const [token, os] of [
    ['FreeBSD', 'bsd'],
    ['OpenBSD', 'bsd'],
    ['NetBSD', 'bsd'],
  ]) {
    const environment = detectEnvironment({
      userAgent: `Mozilla/5.0 (${token}; amd64) AppleWebKit/537.36 Chromium/126.0.0.0 Safari/537.36`,
      maxTouchPoints: 0,
    }, true);
    assert.equal(environment.os, os);
    assert.equal(environment.os_variant, token);
    assert.equal(environment.browser, 'chrome');
  }
  const firefox = detectEnvironment({
    userAgent: 'Mozilla/5.0 (X11; FreeBSD amd64; rv:128.0) Gecko/20100101 Firefox/128.0',
    maxTouchPoints: 0,
  }, true);
  assert.equal(firefox.os, 'bsd');
  assert.equal(firefox.os_variant, 'FreeBSD');
  assert.equal(firefox.browser, 'firefox');
});

test('route selection requires a declared supported platform and matching APIs', () => {
  const config = {
    contract: {
      platforms: [{ os: 'ios', status: 'supported' }],
    },
    routes: [
      {
        os: 'ios',
        browser: 'bluefy',
        transport: 'ble',
        kind: 'web_bluetooth',
        support: 'caveat',
        caveats: ['bluefy_notifications'],
        caveat_text: { bluefy_notifications: 'Bluefy caveat' },
      },
      {
        os: 'ios',
        browser: 'safari',
        transport: 'signal',
        kind: 'websocket',
        support: 'no',
        caveats: [],
        caveat_text: {},
      },
    ],
  };
  const bluefy = {
    os: 'ios',
    browser: 'bluefy',
    secure_context: true,
    max_touch_points: 5,
    capabilities: {
      os: 'ios',
      browser: 'bluefy',
      secure_context: true,
      web_bluetooth: true,
      webusb: false,
      web_serial: false,
      websocket: true,
      webrtc: true,
      webmcp: false,
    },
  };
  const selection = selectRoutes(config, bluefy);
  assert.deepEqual(selection.usable.map((route) => route.transport), ['ble']);
  assert.equal(selection.unavailable[0].reason, 'Declared for safari, not bluefy.');

  const insecure = selectRoutes(config, {
    ...bluefy,
    secure_context: false,
    capabilities: { ...bluefy.capabilities, secure_context: false },
  });
  assert.equal(insecure.usable.length, 0);
  assert.match(insecure.unavailable[0].reason, /secure context/);
});

test('unsupported and undeclared platforms fail closed with diagnostics', () => {
  const config = {
    contract: {
      platforms: [{ os: 'ios', status: 'unsupported', reason: 'No compatible hardware API.' }],
    },
    routes: [],
  };
  const environment = {
    os: 'ios',
    browser: 'safari',
    secure_context: true,
    max_touch_points: 1,
    capabilities: {
      os: 'ios',
      browser: 'safari',
      secure_context: true,
      web_bluetooth: false,
      webusb: false,
      web_serial: false,
      websocket: true,
      webrtc: true,
      webmcp: false,
    },
  };
  assert.deepEqual(selectRoutes(config, environment), {
    os: 'ios',
    browser: 'safari',
    platform_status: 'unsupported',
    platform_reason: 'No compatible hardware API.',
    usable: [],
    unavailable: [],
  });
  const undeclared = selectRoutes(config, { ...environment, os: 'linux' });
  assert.equal(undeclared.platform_status, 'undeclared');
  assert.match(undeclared.platform_reason ?? '', /not declared/i);
});

test('Servo can use declared network routes without exposing hardware transports', () => {
  const config = {
    contract: {
      platforms: [{ os: 'linux', status: 'supported' }],
    },
    routes: [
      { os: 'linux', browser: 'chrome', transport: 'ws', kind: 'websocket', support: 'yes', caveats: [], caveat_text: {} },
      { os: 'linux', browser: 'chrome', transport: 'serial', kind: 'web_serial', support: 'yes', caveats: [], caveat_text: {} },
    ],
  };
  const environment = detectEnvironment({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) Servo/0.6.0',
    maxTouchPoints: 0,
  }, true);
  environment.capabilities.websocket = true;
  assert.equal(environment.browser, 'servo');
  const selection = selectRoutes(config, environment);
  assert.deepEqual(selection.usable.map((route) => route.transport), ['ws']);
  assert.deepEqual(selection.unavailable.map((route) => route.transport), ['serial']);
});
