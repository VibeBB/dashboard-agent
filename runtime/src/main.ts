import { detectEnvironment, selectRoutes, type RouteSelection } from "./capabilities.ts";
import { DashboardSession } from "./session.ts";
import type { DashboardConfig, TransportConfig } from "./types.ts";
import {
  filterTauriBleDevices,
  filterTauriSerialPorts,
  getTauriBackends,
  registerInjectedTauriBackends,
  type TauriBleDevice,
} from "./transports/tauri.ts";
import { element as make, renderTelemetry as updateTelemetry, setControlsEnabled } from "./ui.ts";
import { registerWebMcp } from "./webmcp.ts";

registerInjectedTauriBackends();

declare global {
  interface Window {
    __dashboard: {
      readonly state: string;
      readonly contract: DashboardConfig;
      readonly capabilities: Record<string, string | boolean>;
      readonly routes: RouteSelection;
      readonly telemetry: Record<string, Record<string, number | boolean>>;
      readonly last_seen: Record<string, number>;
    };
  }
}

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error("Dashboard page is missing a required UI element");
  return element;
}

const dashboard = requiredElement<HTMLElement>("#dashboard");
const connectionPanel = requiredElement<HTMLElement>("#connection-panel");
const caveatNotices = requiredElement<HTMLElement>("#caveat-notices");
const widgetsRoot = requiredElement<HTMLElement>("#widgets");
const diagnostics = requiredElement<HTMLElement>("#diagnostics");
const platformBanner = requiredElement<HTMLElement>("#platform-banner");

const response = await fetch("dashboard.config.json", { cache: "no-store" });
if (!response.ok) throw new Error(`Dashboard configuration failed: ${response.status}`);
const config = await response.json() as DashboardConfig;
const environment = detectEnvironment();
const capabilities = environment.capabilities;
const session = new DashboardSession(config);
const selection = selectRoutes(config, environment);
const platform = selection.os;
const platformConfig = config.contract.platforms.find((item) => item.os === platform);
const platformRoutes = config.routes.filter((route) => route.os === platform && route.browser === environment.browser);
let unregisterWebMcp = (): void => undefined;
type PickerOption = { value: string; label: string };
type PickerState = {
  options: PickerOption[];
  selected: string;
  loading: boolean;
  error: string | null;
  scanController: AbortController | null;
};
const pickerStates = new Map<string, PickerState>();

function pickerState(transportId: string): PickerState {
  let state = pickerStates.get(transportId);
  if (!state) {
    state = { options: [], selected: "", loading: false, error: null, scanController: null };
    pickerStates.set(transportId, state);
  }
  return state;
}

function waitForScanWindow(timeout: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    let timer = 0;
    const finish = (): void => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    timer = window.setTimeout(finish, timeout);
    signal.addEventListener("abort", finish, { once: true });
  });
}

function renderCaveats(): void {
  const seen = new Set<string>();
  for (const route of platformRoutes) {
    for (const caveat of route.caveats) {
      if (seen.has(caveat)) continue;
      seen.add(caveat);
      const notice = make("p", route.caveat_text[caveat] ?? caveat, "notice");
      notice.dataset.caveat = caveat;
      caveatNotices.append(notice);
    }
  }
}

function renderTauriPicker(
  transport: Extract<TransportConfig, { kind: "tauri_ble" | "tauri_serial" }>,
  disabled: boolean,
): void {
  const state = pickerState(transport.id);
  const ble = transport.kind === "tauri_ble";
  const labelText = ble ? "Bluetooth device" : "Serial port";
  const select = make("select");
  const selectId = `tauri-picker-${transport.id}`;
  const label = make("label", labelText);
  label.htmlFor = selectId;
  select.id = selectId;
  select.required = true;
  select.disabled = disabled || state.options.length === 0;
  const placeholder = make("option", ble ? "Scan for devices first" : "List ports first");
  placeholder.value = "";
  placeholder.disabled = true;
  select.append(placeholder);
  const connect = make("button", `Connect via ${transport.kind.replaceAll("_", " ")}`);
  connect.type = "button";
  connect.dataset.transport = transport.id;
  connect.disabled = disabled || !state.selected;
  for (const item of state.options) {
    const option = make("option", item.label);
    option.value = item.value;
    select.append(option);
  }
  select.value = state.selected;
  select.addEventListener("change", () => {
    state.selected = select.value;
    connect.disabled = disabled || !state.selected;
  });

  const scan = make(
    "button",
    state.loading
      ? (ble ? "Cancel Bluetooth scan" : "Listing ports…")
      : (ble ? "Scan for Bluetooth devices" : "List serial ports"),
  );
  scan.type = "button";
  scan.disabled = disabled || (state.loading && !ble);
  scan.addEventListener("click", async () => {
    if (state.loading) {
      state.scanController?.abort();
      return;
    }
    state.loading = true;
    state.error = null;
    const scanController = new AbortController();
    state.scanController = ble ? scanController : null;
    renderConnection();
    try {
      if (transport.kind === "tauri_ble") {
        const backend = getTauriBackends().ble;
        if (!backend) throw new Error("Tauri BLE backend is unavailable");
        if (!(await backend.checkPermissions(true))) {
          throw new Error("Bluetooth permission denied");
        }
        if (scanController.signal.aborted) return;
        const devices = new Map<string, TauriBleDevice>();
        const timeout = 5000;
        try {
          await backend.startScan((found) => {
            for (const device of found) devices.set(device.address, device);
          }, timeout);
          await waitForScanWindow(timeout, scanController.signal);
        } finally {
          await backend.stopScan().catch(() => undefined);
        }
        state.options = filterTauriBleDevices([...devices.values()], transport).map((device) => ({
          value: device.address,
          label: `${device.name || "Bluetooth device"} (${device.address})`,
        }));
      } else {
        const backend = getTauriBackends().serial;
        if (!backend) throw new Error("Tauri serial backend is unavailable");
        const ports = await backend.SerialPort.available_ports();
        state.options = filterTauriSerialPorts(ports, transport).map((port) => ({
          value: port.path,
          label: `${port.path} · ${port.manufacturer} ${port.product} (VID ${port.vid}, PID ${port.pid})`,
        }));
      }
      state.selected = "";
      if (!state.options.length && !scanController.signal.aborted) {
        state.error = `No matching ${ble ? "Bluetooth devices" : "serial ports"} found.`;
      }
    } catch (error) {
      state.error = error instanceof Error ? error.message : String(error);
    } finally {
      state.loading = false;
      state.scanController = null;
      renderConnection();
    }
  });

  connect.addEventListener("click", async () => {
    connect.disabled = true;
    try {
      await session.connect(
        transport,
        ble ? { address: state.selected } : { path: state.selected },
      );
    } catch (error) {
      state.error = error instanceof Error ? error.message : String(error);
    } finally {
      renderConnection();
      renderDiagnostics();
    }
  });

  const picker = make("div", undefined, "tauri-picker");
  picker.append(label, select, scan, connect);
  if (state.error) {
    const error = make("p", state.error, "notice");
    error.setAttribute("role", "alert");
    picker.append(error);
  }
  connectionPanel.append(picker);
}

function renderConnection(): void {
  connectionPanel.replaceChildren();
  const status = make("p", `Connection: ${session.state}`, "connection-state");
  status.setAttribute("role", "status");
  connectionPanel.append(status);
  const disabled = session.state === "connecting" || session.state === "reconnecting";
  for (const route of selection.usable) {
    const transport = config.contract.transports.find((item) => item.id === route.transport);
    if (!transport) continue;
    if (transport.kind === "tauri_ble" || transport.kind === "tauri_serial") {
      renderTauriPicker(transport, disabled);
      continue;
    }
    const label = transport.kind.replaceAll("_", " ");
    const connect = make("button", `Connect via ${label} (${route.browser})`);
    connect.type = "button";
    connect.dataset.transport = transport.id;
    connect.disabled = disabled;
    connect.addEventListener("click", async () => {
      connect.disabled = true;
      try {
        await session.connect(transport as TransportConfig);
      } catch (error) {
        const alert = make("p", error instanceof Error ? error.message : String(error));
        alert.setAttribute("role", "alert");
        connectionPanel.append(alert);
      } finally {
        renderConnection();
        renderDiagnostics();
      }
    });
    connectionPanel.append(connect);
  }
  if (selection.unavailable.length) {
    const list = make("ul");
    list.setAttribute("aria-label", "Unavailable routes");
    for (const route of selection.unavailable) {
      const label = route.transport.replaceAll("-", " ").replaceAll("_", " ");
      list.append(make("li", `${label} (${route.browser}): ${route.reason}`));
    }
    connectionPanel.append(list);
  }
  const disconnect = make("button", "Disconnect");
  disconnect.type = "button";
  disconnect.disabled = session.state === "idle";
  disconnect.addEventListener("click", () => {
    void session.close().then(() => {
      renderConnection();
      renderDiagnostics();
    });
  });
  connectionPanel.append(disconnect);
}

function renderWidgets(): void {
  widgetsRoot.replaceChildren();
  for (const widget of config.contract.widgets) {
    const card = make("article", undefined, "widget");
    card.setAttribute("aria-label", widget.label);
    card.append(make("h2", widget.label));
    if (["value", "gauge", "chart", "indicator"].includes(widget.kind)) {
      const value = make("output", "—");
      const [messageName, fieldName] = widget.source?.split(".", 2) ?? ["", ""];
      value.dataset.message = messageName;
      value.dataset.field = fieldName;
      value.setAttribute("aria-live", "polite");
      if (widget.kind === "gauge") {
        const gauge = make("meter");
        const fieldConfig = config.contract.protocol.messages
          .find((item) => item.name === messageName)
          ?.fields.find((item) => item.name === fieldName);
        gauge.min = fieldConfig?.min ?? 0;
        gauge.max = fieldConfig?.max ?? 100;
        gauge.value = gauge.min;
        gauge.setAttribute("aria-label", widget.label);
        card.append(gauge);
      }
      if (widget.kind === "chart") {
        const canvas = make("canvas");
        canvas.width = 600;
        canvas.height = 160;
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", `${widget.label} history`);
        card.append(canvas);
      }
      card.append(value);
    } else {
      const command = config.contract.protocol.messages.find((message) => message.name === widget.command);
      if (!command) {
        widgetsRoot.append(card);
        continue;
      }
      const controls = new Map<string, HTMLInputElement>();
      for (const field of command.fields) {
        const label = make("label", field.name);
        const input = make("input");
        input.name = field.name;
        input.type = field.type === "bool" ? "checkbox" : widget.kind === "slider" ? "range" : "number";
        input.dataset.field = field.name;
        if (field.min !== null && field.min !== undefined) input.min = String(field.min);
        if (field.max !== null && field.max !== undefined) input.max = String(field.max);
        if (input.type === "range" && field.scale > 0) input.step = String(field.scale);
        label.append(input);
        card.append(label);
        controls.set(field.name, input);
      }
      const send = make("button", widget.kind === "toggle" ? "Apply" : "Send");
      send.type = "button";
      send.disabled = session.state !== "connected";
      send.addEventListener("click", async () => {
        const values: Record<string, number | boolean> = {};
        for (const [name, control] of controls) {
          values[name] = control.type === "checkbox" ? control.checked : Number(control.value);
        }
        try {
          await session.sendCommand(command.name, values, { hazard: widget.hazard });
        } catch (error) {
          const alert = make("p", error instanceof Error ? error.message : String(error));
          alert.setAttribute("role", "alert");
          card.append(alert);
        }
      });
      card.append(send);
    }
    widgetsRoot.append(card);
  }
}

function renderDiagnostics(): void {
  diagnostics.textContent = JSON.stringify({
    design: config.contract.name,
    platform,
    os_variant: environment.os_variant,
    platform_status: platformConfig?.status ?? "undeclared",
    platform_reason: platformConfig?.reason ?? selection.platform_reason,
    browser: environment.browser,
    secure_context: environment.secure_context,
    state: session.state,
    capabilities,
    webmcp: capabilities.webmcp,
    usable_routes: selection.usable.map((route) => ({
      transport: route.transport,
      browser: route.browser,
      support: route.support,
      caveats: route.caveats,
    })),
    unavailable_routes: selection.unavailable.map((route) => ({
      transport: route.transport,
      browser: route.browser,
      reason: route.reason,
    })),
    contract_sha256: config.contract_sha256,
  }, null, 2);
}

platformBanner.textContent = selection.platform_status === "unsupported"
  ? `${platform} is unsupported: ${selection.platform_reason ?? "No supported route is declared."}`
  : selection.platform_status === "undeclared"
    ? `${platform} is not declared for this dashboard.`
    : `${platform} dashboard · ${environment.browser}`;
if (selection.platform_status !== "supported") {
  platformBanner.setAttribute("role", "alert");
  platformBanner.className = "unsupported";
  widgetsRoot.hidden = true;
}
renderCaveats();
renderConnection();
renderWidgets();
setControlsEnabled(widgetsRoot, session.state);
renderDiagnostics();

Object.defineProperty(window, "__dashboard", {
  configurable: false,
  value: {
    get state() { return session.state; },
    contract: config,
    capabilities,
    routes: selection,
    get telemetry() { return session.telemetry; },
    get last_seen() { return session.lastSeen; },
  },
});

session.addEventListener("statechange", () => {
  renderConnection();
  setControlsEnabled(widgetsRoot, session.state);
  renderDiagnostics();
});
session.addEventListener("telemetry", () => updateTelemetry(widgetsRoot, session.telemetry));
session.addEventListener("protocolerror", (event) => {
  const alert = make("p", String((event as CustomEvent<unknown>).detail), "notice");
  alert.setAttribute("role", "alert");
  connectionPanel.append(alert);
});

unregisterWebMcp = await registerWebMcp(config, session, () => ({
  design: config.contract.name,
  state: session.state,
  platform,
  browser: environment.browser,
  platform_status: selection.platform_status,
  platform_reason: selection.platform_reason,
  usable_routes: selection.usable,
  unavailable_routes: selection.unavailable,
  caveats: [...new Set(platformRoutes.flatMap((route) => route.caveats))],
}));
window.addEventListener("pagehide", () => {
  unregisterWebMcp();
  void session.close();
}, { once: true });
