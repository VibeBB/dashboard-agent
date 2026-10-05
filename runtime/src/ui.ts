import type { SessionState } from "./session.ts";
import type { TelemetryValues } from "./types.ts";

export function element<K extends keyof HTMLElementTagNameMap>(
  name: K,
  text?: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const result = document.createElement(name);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

export function formatFieldValue(value: string | number | boolean, unit?: string | null): string {
  const rendered = typeof value === "boolean" ? (value ? "On" : "Off") : String(value);
  return unit ? `${rendered} ${unit}` : rendered;
}

export function formatFieldLabel(name: string, unit?: string | null): string {
  const rendered = name.replaceAll("_", " ");
  return unit ? `${rendered} (${unit})` : rendered;
}

export function renderTelemetry(root: HTMLElement, values: TelemetryValues): void {
  for (const output of root.querySelectorAll<HTMLOutputElement>("output[data-message]")) {
    const message = output.dataset.message ?? "";
    const field = output.dataset.field ?? "";
    const messageValues = values[message];
    if (!messageValues || !(field in messageValues)) continue;
    const value = messageValues[field];
    output.value = formatFieldValue(value, output.dataset.unit);
    const meter = output.parentElement?.querySelector("meter");
    if (meter && typeof value === "number") {
      meter.value = Math.max(meter.min, Math.min(meter.max, value));
    }
    const canvas = output.parentElement?.querySelector("canvas");
    if (canvas && typeof value === "number") {
      const history = JSON.parse(output.dataset.history ?? "[]") as number[];
      history.push(value);
      output.dataset.history = JSON.stringify(history.slice(-60));
      const context = canvas.getContext("2d");
      if (context) {
        const data = history.slice(-60);
        const minimum = Math.min(...data);
        const maximum = Math.max(...data);
        const span = maximum - minimum || 1;
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.beginPath();
        data.forEach((point, index) => {
          const x = data.length < 2 ? canvas.width / 2 : (index / (data.length - 1)) * canvas.width;
          const y = canvas.height - ((point - minimum) / span) * canvas.height;
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        context.strokeStyle = "#70d6c7";
        context.stroke();
      }
    }
  }
}

export function setControlsEnabled(root: HTMLElement, state: SessionState): void {
  for (const control of root.querySelectorAll<HTMLButtonElement>(".widget button")) {
    control.disabled = state !== "connected";
  }
}
