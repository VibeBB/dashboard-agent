import { detectEnvironment, selectRoutes, type RouteSelection } from "./capabilities.ts";
import { DashboardSession } from "./session.ts";
import type { DashboardConfig, TransportConfig } from "./types.ts";
import { element as make, renderTelemetry as updateTelemetry, setControlsEnabled } from "./ui.ts";
import { registerWebMcp } from "./webmcp.ts";

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

function renderConnection(): void {
  connectionPanel.replaceChildren();
  const status = make("p", `Connection: ${session.state}`, "connection-state");
  status.setAttribute("role", "status");
  connectionPanel.append(status);
  const disabled = session.state === "connecting" || session.state === "reconnecting";
  for (const route of selection.usable) {
    const transport = config.contract.transports.find((item) => item.id === route.transport);
    if (!transport) continue;
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
