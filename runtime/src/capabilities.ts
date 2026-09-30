import type { DashboardConfig, TransportKind } from "./types.ts";
import { hasTauriBackend, isTauriRuntime } from "./transports/tauri.ts";

export interface CapabilityReport {
  os: string;
  browser: string;
  secure_context: boolean;
  web_bluetooth: boolean;
  webusb: boolean;
  web_serial: boolean;
  websocket: boolean;
  webrtc: boolean;
  webmcp: boolean;
  tauri_ble: boolean;
  tauri_serial: boolean;
}

export interface BrowserEnvironment {
  os: string;
  os_variant: string | null;
  browser: string;
  secure_context: boolean;
  max_touch_points: number;
  capabilities: CapabilityReport;
}

export interface SelectedRoute {
  os: string;
  browser: string;
  transport: string;
  kind: TransportKind;
  support: string;
  caveats: string[];
  caveat_text: Record<string, string>;
  available: boolean;
  reason: string;
}

export interface RouteSelection {
  os: string;
  browser: string;
  platform_status: "supported" | "unsupported" | "undeclared";
  platform_reason: string | null;
  usable: SelectedRoute[];
  unavailable: SelectedRoute[];
}

interface NavigatorWithUaData extends Navigator {
  userAgentData?: { platform?: string; brands?: Array<{ brand: string }> };
}

function osFromStrings(platform: string, userAgent: string, touchPoints: number): string {
  if (/iPad/i.test(userAgent) || (/Macintosh/i.test(userAgent) && touchPoints > 1)) return "ipados";
  if (/iPhone|iPod/i.test(userAgent)) return "ios";
  if (/FreeBSD|OpenBSD|NetBSD/i.test(userAgent)) return "bsd";
  if (/^iPadOS$/i.test(platform)) return "ipados";
  if (/^iOS$/i.test(platform)) return "ios";
  const source = platform || userAgent;
  if (/Android/i.test(source)) return "android";
  if (/CrOS/i.test(source) || /Chrome OS/i.test(platform)) return "chromeos";
  if (/Windows/i.test(source)) return "windows";
  if (/Mac/i.test(source)) return "macos";
  if (/Linux/i.test(source)) return "linux";
  return "unknown";
}

function bsdVariantFromUserAgent(userAgent: string): string | null {
  const match = userAgent.match(/\b(FreeBSD|OpenBSD|NetBSD)\b/i);
  switch (match?.[1]?.toLowerCase()) {
    case "freebsd":
      return "FreeBSD";
    case "openbsd":
      return "OpenBSD";
    case "netbsd":
      return "NetBSD";
    default:
      return null;
  }
}

function browserFromStrings(
  userAgent: string,
  brands: Array<{ brand: string }>,
  os: string,
  hasBluetooth: boolean,
): string {
  const source = `${userAgent} ${brands.map((brand) => brand.brand).join(" ")}`;
  if (/Bluefy/i.test(source) || (["ios", "ipados"].includes(os) && hasBluetooth)) return "bluefy";
  if (/Servo/i.test(source)) return "servo";
  if (/SamsungBrowser/i.test(source)) return "samsung_internet";
  if (/OPR\/|Opera/i.test(source)) return "opera";
  if (/Edg\//i.test(source) || /Microsoft Edge/i.test(source)) return "edge";
  if (/Firefox|FxiOS/i.test(source)) return "firefox";
  if (/Chrome|CriOS|Chromium|Google Chrome/i.test(source)) return "chrome";
  if (/Safari/i.test(source)) return "safari";
  return "unknown";
}

export function detectEnvironment(
  targetNavigator: NavigatorWithUaData = navigator,
  secureContext = globalThis.isSecureContext,
): BrowserEnvironment {
  const uaData = targetNavigator.userAgentData;
  const userAgent = targetNavigator.userAgent;
  const maxTouchPoints = targetNavigator.maxTouchPoints ?? 0;
  const os = osFromStrings(uaData?.platform ?? "", userAgent, maxTouchPoints);
  const osVariant = bsdVariantFromUserAgent(userAgent);
  const hasBluetooth = "bluetooth" in targetNavigator;
  const browser = isTauriRuntime()
    ? "tauri"
    : browserFromStrings(userAgent, uaData?.brands ?? [], os, hasBluetooth);
  return {
    os,
    os_variant: osVariant,
    browser,
    secure_context: secureContext,
    max_touch_points: maxTouchPoints,
    capabilities: {
      os,
      browser,
      secure_context: secureContext,
      web_bluetooth: hasBluetooth,
      webusb: "usb" in targetNavigator,
      web_serial: "serial" in targetNavigator,
      websocket: typeof WebSocket !== "undefined",
      webrtc: typeof RTCPeerConnection !== "undefined",
      webmcp: Boolean(
        typeof document !== "undefined" &&
          document.modelContext &&
          "registerTool" in document.modelContext,
      ),
      tauri_ble: hasTauriBackend("tauri_ble"),
      tauri_serial: hasTauriBackend("tauri_serial"),
    },
  };
}

export function getCapabilities(): CapabilityReport {
  return detectEnvironment().capabilities;
}

function routeAvailable(kind: TransportKind, environment: BrowserEnvironment): boolean {
  const capabilities = environment.capabilities;
  if (kind === "web_bluetooth") return capabilities.web_bluetooth && capabilities.secure_context;
  if (kind === "webusb") return capabilities.webusb && capabilities.secure_context;
  if (kind === "web_serial") return capabilities.web_serial && capabilities.secure_context;
  if (kind === "tauri_ble") return capabilities.tauri_ble;
  if (kind === "tauri_serial") return capabilities.tauri_serial;
  if (kind === "webrtc") return capabilities.webrtc && capabilities.secure_context;
  return capabilities.websocket;
}

export function selectRoutes(config: DashboardConfig, environment: BrowserEnvironment): RouteSelection {
  const declaration = config.contract.platforms.find((item) => item.os === environment.os);
  const platformStatus = declaration?.status ?? "undeclared";
  const declared = config.routes.filter((route) => route.os === environment.os);
  const routes = declared.map((route): SelectedRoute => {
    const browserMatches =
      route.browser === environment.browser ||
      (environment.browser === "servo" && ["websocket", "webrtc"].includes(route.kind));
    const browserSupported = route.support !== "no";
    const apiAvailable = routeAvailable(route.kind, environment);
    const available = platformStatus === "supported" && browserMatches && browserSupported && apiAvailable;
    let reason = "";
    if (platformStatus === "unsupported") reason = declaration?.reason ?? "Platform is unsupported.";
    else if (platformStatus === "undeclared") reason = "Platform is not declared by this dashboard.";
    else if (!browserMatches) reason = `Declared for ${route.browser}, not ${environment.browser}.`;
    else if (!browserSupported) reason = "This browser and transport combination is unsupported.";
    else if (!apiAvailable) reason = `Required ${route.kind} API is unavailable or the page is not a secure context.`;
    return { ...route, available, reason };
  });
  return {
    os: environment.os,
    browser: environment.browser,
    platform_status: platformStatus,
    platform_reason: declaration?.reason
      ?? (platformStatus === "undeclared" ? "Platform is not declared by this dashboard." : null),
    usable: routes.filter((route) => route.available),
    unavailable: routes.filter((route) => !route.available),
  };
}

export function transportCapability(kind: TransportKind, capabilities: CapabilityReport): boolean {
  type CapabilityFlag =
    | "web_bluetooth"
    | "webusb"
    | "web_serial"
    | "websocket"
    | "webrtc"
    | "tauri_ble"
    | "tauri_serial";
  const keys: Record<TransportKind, CapabilityFlag> = {
    web_bluetooth: "web_bluetooth",
    webusb: "webusb",
    web_serial: "web_serial",
    websocket: "websocket",
    webrtc: "webrtc",
    tauri_ble: "tauri_ble",
    tauri_serial: "tauri_serial",
  };
  return capabilities[keys[kind]];
}
