interface ModelContextTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: {
    readOnlyHint?: boolean;
    untrustedContentHint?: boolean;
    consequentialHint?: boolean;
  };
  execute: (input: unknown) => unknown | Promise<unknown>;
}

interface DocumentModelContext {
  registerTool(tool: ModelContextTool, options?: { signal?: AbortSignal }): Promise<void> | void;
  getTools?: () => Promise<Array<{ name: string }>>;
  executeTool?: (tool: unknown, input: string) => Promise<string>;
}

interface Document {
  modelContext?: DocumentModelContext;
}
