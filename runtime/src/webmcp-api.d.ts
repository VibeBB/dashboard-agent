export {};

declare global {
  interface DashboardModelContextTool {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
    annotations: {
      readOnlyHint?: boolean;
      untrustedContentHint?: boolean;
      consequentialHint?: boolean;
    };
    execute: (input: unknown) => unknown | Promise<unknown>;
  }

  interface DashboardModelContext {
    registerTool(
      tool: DashboardModelContextTool,
      options?: { signal?: AbortSignal },
    ): void | Promise<void>;
    getTools?: () => Promise<DashboardModelContextTool[]>;
    executeTool?: (tool: DashboardModelContextTool, input: string) => Promise<string>;
  }

  interface Document {
    modelContext?: DashboardModelContext;
  }
}
