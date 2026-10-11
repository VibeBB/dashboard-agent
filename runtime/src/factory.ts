export interface FactoryCommand {
  id: string;
  name: string;
  request: string;
  response_pattern: string;
  timeout_ms: number;
  destructive: boolean;
}

export interface FactoryConfig {
  spec_sha256: string;
  transport: string;
  commands: FactoryCommand[];
  exit: string;
}

export interface FactoryResult {
  id: string;
  status: "pass" | "fail";
  line: string;
}

export interface LineIo {
  send(line: string): Promise<void>;
  nextLine(timeoutMs: number): Promise<string | null>;
}

const PLACEHOLDER = /<([A-Za-z0-9_]+)>/g;

export function placeholders(commands: readonly FactoryCommand[]): string[] {
  const names: string[] = [];
  for (const command of commands) {
    for (const text of [command.request, command.response_pattern]) {
      for (const match of text.matchAll(PLACEHOLDER)) {
        if (!names.includes(match[1])) names.push(match[1]);
      }
    }
  }
  return names;
}

export function fillTemplate(template: string, values: Readonly<Record<string, string>>): string {
  return template.replace(PLACEHOLDER, (_, name: string) => {
    const value = values[name]?.trim() ?? "";
    if (!value || /[\r\n]/.test(value)) throw new Error(`Factory value <${name}> is missing or multi-line`);
    return value;
  });
}

export class LineBuffer {
  readonly #decoder = new TextDecoder();
  #pending = "";

  push(bytes: Uint8Array): string[] {
    this.#pending += this.#decoder.decode(bytes, { stream: true });
    const lines = this.#pending.split("\n");
    this.#pending = lines.pop() ?? "";
    return lines.map((line) => line.replace(/\r$/, ""));
  }
}

export function lineIo(transport: {
  send(bytes: Uint8Array): Promise<void>;
  onBytes?(callback: (bytes: Uint8Array) => void): void;
}): LineIo {
  if (!transport.onBytes) throw new Error("Factory transport cannot read raw bytes");
  const buffer = new LineBuffer();
  const queue: string[] = [];
  let waiter: ((line: string) => void) | null = null;
  transport.onBytes((bytes) => {
    for (const line of buffer.push(bytes)) {
      if (waiter) {
        const wake = waiter;
        waiter = null;
        wake(line);
      } else queue.push(line);
    }
  });
  return {
    send: (line) => transport.send(new TextEncoder().encode(line)),
    nextLine: (timeoutMs) => {
      const queued = queue.shift();
      if (queued !== undefined) return Promise.resolve(queued);
      return new Promise((resolve) => {
        const timer = setTimeout(() => {
          waiter = null;
          resolve(null);
        }, timeoutMs);
        waiter = (line) => {
          clearTimeout(timer);
          resolve(line);
        };
      });
    },
  };
}

export async function runFactory(
  io: LineIo,
  commands: readonly FactoryCommand[],
  values: Readonly<Record<string, string>>,
  confirm: (command: FactoryCommand) => boolean,
  now: () => number = () => Date.now(),
): Promise<FactoryResult[]> {
  const results: FactoryResult[] = [];
  for (const command of commands) {
    if (command.destructive && !confirm(command)) {
      results.push({ id: command.id, status: "fail", line: "cancelled by operator" });
      break;
    }
    const expected = fillTemplate(command.response_pattern, values);
    await io.send(`${fillTemplate(command.request, values)}\n`);
    const deadline = now() + command.timeout_ms;
    let result: FactoryResult = { id: command.id, status: "fail", line: "timeout" };
    for (let remaining = command.timeout_ms; remaining > 0; remaining = deadline - now()) {
      const line = await io.nextLine(remaining);
      if (line === null) break;
      result = { id: command.id, status: line.trim() === expected ? "pass" : "fail", line };
      if (result.status === "pass") break;
    }
    results.push(result);
    if (result.status === "fail") break;
  }
  return results;
}
