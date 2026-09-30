import type { DashboardConfig, WebMcpToolDefinition } from "./types.ts";
import type { DashboardSession } from "./session.ts";

function validArguments(input: unknown): Record<string, unknown> {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    throw new TypeError("Tool arguments must be an object");
  }
  return input as Record<string, unknown>;
}

export async function registerWebMcp(
  config: DashboardConfig,
  session: DashboardSession,
  status: () => object,
): Promise<() => void> {
  if (!config.contract.webmcp?.enabled) return () => undefined;
  const context = document.modelContext;
  if (!context || !("registerTool" in context) || typeof context.registerTool !== "function") {
    return () => undefined;
  }
  const controller = new AbortController();
  const tools = config.webmcp_tools;
  try {
    for (const definition of tools) {
      const execute = createExecutor(definition, config, session, status);
      await context.registerTool(
        {
          name: definition.name,
          description: definition.description,
          inputSchema: definition.inputSchema,
          annotations: definition.annotations,
          execute,
        },
        { signal: controller.signal },
      );
    }
  } catch (error) {
    controller.abort();
    throw error;
  }
  return () => controller.abort();
}

function createExecutor(
  definition: WebMcpToolDefinition,
  config: DashboardConfig,
  session: DashboardSession,
  status: () => object,
): (input: unknown) => Promise<unknown> {
  if (definition.name === "dashboard_status") {
    return async () => {
      const current = status();
      return session.state === "connected"
        ? current
        : { ...current, instruction: "Ask the user to click Connect to select a device." };
    };
  }
  if (definition.name === "read_telemetry") {
    return async (input) => {
      const args = validArguments(input);
      const message = args.message;
      const telemetry = session.telemetry;
      if (typeof message === "string") {
        return { message, values: telemetry[message] ?? null, timestamp_ms: session.lastSeen[message] ?? null };
      }
      return {
        messages: Object.fromEntries(
          Object.entries(telemetry).map(([name, values]) => [name, { values, timestamp_ms: session.lastSeen[name] }]),
        ),
      };
    };
  }
  const messageName = definition.name.startsWith("send_") ? definition.name.slice("send_".length) : "";
  const message = config.contract.protocol.messages.find(
    (candidate) => candidate.name === messageName && candidate.direction === "host_to_device",
  );
  if (!message) {
    return async () => {
      throw new Error(`Unknown WebMCP tool ${definition.name}`);
    };
  }
  const hazard = definition.annotations.consequentialHint === true;
  return async (input) => {
    const args = validArguments(input);
    return session.sendCommand(message.name, args, {
      hazard,
      confirm: () => window.confirm(`Allow ${message.name} on ${config.contract.name}?`),
    });
  };
}
