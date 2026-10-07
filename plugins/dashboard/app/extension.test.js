import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { __internals, activate } from "./extension.js";

// Minimal DOM double: the extension only uses createElement/textContent,
// append/appendChild, className, addEventListener, remove, and type/disabled.
class FakeEl {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this._text = "";
    this.className = "";
    this.type = "";
    this.disabled = false;
    this.listeners = {};
    this.parent = null;
    this.removed = false;
  }

  append(...nodes) {
    for (const node of nodes) {
      if (node && typeof node === "object") node.parent = this;
      this.children.push(node);
    }
  }

  appendChild(node) {
    if (node && typeof node === "object") node.parent = this;
    this.children.push(node);
    return node;
  }

  set textContent(value) {
    this._text = value == null ? "" : String(value);
    this.children = [];
  }

  get textContent() {
    return this._text + this.children.map((c) => c.textContent || "").join("");
  }

  addEventListener(type, fn) {
    (this.listeners[type] = this.listeners[type] || []).push(fn);
  }

  click() {
    for (const fn of this.listeners.click || []) fn({});
  }

  remove() {
    this.removed = true;
    if (this.parent) {
      const idx = this.parent.children.indexOf(this);
      if (idx >= 0) this.parent.children.splice(idx, 1);
      this.parent = null;
    }
  }
}

globalThis.document = {
  createElement: (tag) => new FakeEl(tag),
  createTextNode: (text) => ({ textContent: String(text) }),
};

function tick(times = 20) {
  let p = Promise.resolve();
  for (let i = 0; i < times; i += 1) {
    p = p.then(() => new Promise((r) => setTimeout(r, 0)));
  }
  return p;
}

const REPORT = {
  system: "dashboard",
  artifact_kind: "dashboard_gate_report",
  design: "smart-kettle",
  scope: "static",
  contract_sha256: "abc123",
  verdict: "pass",
  checks: [
    { id: "contract.parses", status: "pass", detail: "ok", evidence: ["contract.json"] },
    { id: "app.index", status: "fail", detail: "missing index", evidence: [] },
  ],
};

function makeHost(routes) {
  const navigations = [];
  let mountFn = null;
  const host = {
    apiVersion: "1",
    extension: { name: "dashboard-reports", version: "0.1.0", resolvedRef: "test" },
    backend: { id: "backend-1", kind: "local", orgId: "org" },
    registerPage(id, mount) {
      assert.equal(id, "reports");
      mountFn = mount;
      return () => {
        mountFn = null;
      };
    },
    navigate(path) {
      navigations.push(path);
    },
    agentServer: {
      request: async ({ path }) => {
        for (const [pattern, handler] of Object.entries(routes)) {
          if (pattern.endsWith("*")) {
            if (path.startsWith(pattern.slice(0, -1))) return handler(path);
          } else if (path === pattern) {
            return handler(path);
          }
        }
        throw new Error(`GET ${path} -> 404 Not Found`);
      },
    },
  };
  return {
    host,
    navigations,
    mount(path = "") {
      const container = new FakeEl("div");
      const dispose = mountFn({ container, path, navigate: host.navigate });
      return { container, dispose };
    },
  };
}

function standardRoutes() {
  return {
    "/api/conversations/search*": () => ({
      items: [
        {
          id: "conv-1",
          title: "kettle dashboard",
          workspace: { kind: "LocalWorkspace", working_dir: "/ws/conv-1" },
        },
        {
          id: "conv-2",
          title: "remote one",
          workspace: { kind: "RemoteWorkspace", working_dir: "/remote" },
        },
      ],
      next_page_id: null,
    }),
    "/api/workspaces": () => ({ workspaces: [] }),
    "/api/file/search_subdirs*": (path) => {
      const dir = decodeURIComponent(new URLSearchParams(path.split("?")[1]).get("path"));
      if (dir === "/ws/conv-1")
        return { items: [{ name: "examples", path: "/ws/conv-1/examples" }], next_page_id: null };
      if (dir === "/ws/conv-1/examples")
        return {
          items: [{ name: "smart-kettle", path: "/ws/conv-1/examples/smart-kettle" }],
          next_page_id: null,
        };
      if (dir === "/ws/conv-1/examples/smart-kettle")
        return {
          items: [{ name: "out", path: "/ws/conv-1/examples/smart-kettle/out" }],
          next_page_id: null,
        };
      if (dir === "/ws/conv-1/examples/smart-kettle/out")
        return {
          items: [
            { name: "smart-kettle", path: "/ws/conv-1/examples/smart-kettle/out/smart-kettle" },
          ],
          next_page_id: null,
        };
      return { items: [], next_page_id: null };
    },
    "/api/file/download*": (path) => {
      const file = decodeURIComponent(new URLSearchParams(path.split("?")[1]).get("path"));
      if (file === "/ws/conv-1/examples/smart-kettle/out/smart-kettle.dash-report.json")
        return REPORT;
      throw new Error(`GET ${path} -> 404 Not Found`);
    },
  };
}

describe("activate", () => {
  it("registers the reports page and returns a disposer", () => {
    const host = makeHost(standardRoutes());
    const unregister = activate(host.host);
    assert.equal(typeof unregister, "function");
    unregister();
  });

  it("rejects unsupported host API versions", () => {
    const host = makeHost(standardRoutes());
    host.host.apiVersion = "2";
    assert.throws(() => activate(host.host), /host API 1/);
  });
});

describe("reports list view", () => {
  it("discovers a gate report under out/ and renders the verdict", async () => {
    const host = makeHost(standardRoutes());
    activate(host.host);
    const { container } = host.mount("");
    await tick();
    const text = container.textContent;
    assert.match(text, /smart-kettle/);
    assert.match(text, /pass/);
    assert.match(text, /generated app/);
    assert.match(text, /1 artifact/);
  });

  it("navigates to the detail route when the design link is clicked", async () => {
    const host = makeHost(standardRoutes());
    activate(host.host);
    const { container } = host.mount("");
    await tick();
    const links = [];
    const walk = (node) => {
      for (const child of node.children || []) {
        if (child.className === "dbr-link") links.push(child);
        walk(child);
      }
    };
    walk(container);
    assert.equal(links.length, 1);
    links[0].click();
    assert.equal(host.navigations.length, 1);
    assert.match(host.navigations[0], /^\/extensions\/dashboard-reports\/reports\/view\//);
  });

  it("shows an empty state when no workspaces exist", async () => {
    const host = makeHost({
      "/api/conversations/search*": () => ({ items: [], next_page_id: null }),
      "/api/workspaces": () => ({ workspaces: [] }),
    });
    activate(host.host);
    const { container } = host.mount("");
    await tick();
    assert.match(container.textContent, /No local workspaces found/);
  });
});

describe("report detail view", () => {
  it("renders verdict banner, metadata, and the checks table", async () => {
    const host = makeHost(standardRoutes());
    activate(host.host);
    const { container } = host.mount(
      "view/" +
        __internals.encodeReportPath(
          "/ws/conv-1/examples/smart-kettle/out/smart-kettle.dash-report.json",
        ),
    );
    await tick();
    const text = container.textContent;
    assert.match(text, /Verdict: pass/);
    assert.match(text, /1 pass.*1 fail|1 pass, 1 fail/);
    assert.match(text, /contract\.parses/);
    assert.match(text, /missing index/);
    assert.match(text, /abc123/);
    assert.match(text, /"artifact_kind": "dashboard_gate_report"/);
  });

  it("reports an error for a missing report file", async () => {
    const host = makeHost(standardRoutes());
    activate(host.host);
    const { container } = host.mount("view/nope.dash-report.json");
    await tick();
    assert.match(container.textContent, /Could not load report/);
  });
});

describe("internals", () => {
  it("round-trips encoded absolute paths", () => {
    const abs = "/ws/conv-1/out/smart kettle.dash-report.json";
    const encoded = __internals.encodeReportPath(abs);
    assert.equal(encoded, "/ws/conv-1/out/smart%20kettle.dash-report.json");
    assert.equal(__internals.decodeReportPath(encoded.slice(1)), abs);
  });

  it("normalizes foreign payloads to null", () => {
    assert.equal(__internals.normalizeReport({ artifact_kind: "other" }), null);
    assert.equal(__internals.normalizeReport("nope"), null);
    const report = __internals.normalizeReport(REPORT);
    assert.equal(report.verdict, "pass");
    assert.equal(report.checks.length, 2);
    assert.equal(__internals.checksSummary(report), "1 pass, 1 fail");
  });

  it("derives basename/dirname from absolute paths", () => {
    assert.equal(__internals.basename("/a/b/out"), "out");
    assert.equal(__internals.dirname("/a/b/out"), "/a/b");
    assert.equal(__internals.dirname("/out"), "/");
  });
});
