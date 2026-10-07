/*
 * Dashboard reports — Agent Canvas app (canvas-extension schema 1, host API 1).
 *
 * Read-only viewer for dashboard gate reports (`*.dash-report.json`) produced
 * by the dashboard plugin inside local workspaces on the active Agent Server.
 *
 * Discovery constraint: the Agent Server file API lists directories only
 * (`GET /api/file/search_subdirs`), so this extension scans each local
 * workspace for generated `out/` trees and probes
 * `<out>/<design>.dash-report.json` for every directory name found inside
 * `out/` (the generated app directory name mirrors the contract name) plus
 * the name of the directory that owns `out/` (the contract directory).
 */

const PAGE_ID = "reports";
const EXT_ROOT = "/extensions/dashboard-reports/reports";
const REPORT_SUFFIX = ".dash-report.json";
const REPORT_KIND = "dashboard_gate_report";

const MAX_SCAN_DEPTH = 5;
const MAX_DIRS_PER_WORKSPACE = 400;
const MAX_SUBDIR_PAGES = 20;
const MAX_CONVERSATION_PAGES = 5;
const FETCH_CONCURRENCY = 4;
const SKIP_DIRS = new Set([
  ".git",
  ".venv",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "site-packages",
  "target",
]);

const STYLES = `
.dbr{color:var(--oh-foreground,#EEF2F7);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:16px 20px;max-width:1100px}
.dbr *{box-sizing:border-box}
.dbr-head{margin-bottom:12px}
.dbr-title{font-size:20px;font-weight:650;margin:0 0 4px}
.dbr-sub{color:var(--oh-muted,#A3B0C4);margin:0 0 10px}
.dbr-mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;word-break:break-all}
.dbr-status{color:var(--oh-muted,#A3B0C4);margin:8px 0}
.dbr-error{color:var(--oh-danger,#E76A5E)}
.dbr-warn{color:var(--oh-muted,#A3B0C4)}
.dbr-btn{background:var(--oh-surface-raised,#2C313F);color:var(--oh-foreground,#EEF2F7);border:1px solid var(--oh-border,#4B5468);border-radius:6px;padding:5px 12px;font:inherit;cursor:pointer}
.dbr-btn:hover{border-color:var(--oh-color-primary,#C9B974)}
.dbr-btn:disabled{opacity:.5;cursor:default}
.dbr-link{background:none;border:none;color:var(--oh-color-primary,#C9B974);font:inherit;cursor:pointer;padding:0;text-align:left}
.dbr-link:hover{text-decoration:underline}
.dbr-table{border-collapse:collapse;width:100%;margin-top:8px}
.dbr-th,.dbr-td{border-bottom:1px solid var(--oh-border-subtle,#383F50);padding:8px 10px;text-align:left;vertical-align:top}
.dbr-th{color:var(--oh-text-dim,#7E8A9E);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.dbr-badge{display:inline-block;border-radius:10px;padding:1px 9px;font-size:12px;font-weight:600}
.dbr-badge-ok{background:rgba(165,231,94,.15);color:var(--oh-success,#A5E75E)}
.dbr-badge-bad{background:rgba(231,106,94,.15);color:var(--oh-danger,#E76A5E)}
.dbr-badge-dim{background:var(--oh-surface-raised,#2C313F);color:var(--oh-muted,#A3B0C4)}
.dbr-path{color:var(--oh-text-dim,#7E8A9E);font-size:12px;word-break:break-all}
.dbr-panel{background:var(--oh-color-base-secondary,#21252F);border:1px solid var(--oh-border-subtle,#383F50);border-radius:8px;padding:14px 16px;margin:12px 0}
.dbr-meta{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0;font-size:13px}
.dbr-meta dt{color:var(--oh-text-dim,#7E8A9E)}
.dbr-meta dd{margin:0;word-break:break-all}
.dbr-check-status{width:110px}
.dbr-detail{color:var(--oh-muted,#A3B0C4)}
.dbr-evidence{margin:6px 0 0;padding-left:16px;font-size:12px;color:var(--oh-text-dim,#7E8A9E)}
.dbr-pre{max-height:480px;overflow:auto;background:var(--oh-color-base,#0B0E14);border:1px solid var(--oh-border-subtle,#383F50);border-radius:6px;padding:12px;font-size:12px;white-space:pre-wrap;word-break:break-word}
.dbr-details summary{cursor:pointer;color:var(--oh-muted,#A3B0C4);margin:12px 0 6px}
.dbr-verdict-banner{border-radius:8px;padding:10px 14px;font-weight:650;margin:12px 0}
.dbr-verdict-pass{background:rgba(165,231,94,.12);border:1px solid var(--oh-success,#A5E75E);color:var(--oh-success,#A5E75E)}
.dbr-verdict-fail{background:rgba(231,106,94,.12);border:1px solid var(--oh-danger,#E76A5E);color:var(--oh-danger,#E76A5E)}
.dbr-verdict-other{background:var(--oh-color-base-secondary,#21252F);border:1px solid var(--oh-border,#4B5468)}
`;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function msg(err) {
  return err && err.message ? String(err.message) : String(err);
}

function isNotFound(err) {
  return /404|not found/i.test(msg(err));
}

function basename(path) {
  const clean = path.replace(/\/+$/, "");
  const idx = clean.lastIndexOf("/");
  return idx < 0 ? clean : clean.slice(idx + 1);
}

function dirname(path) {
  const clean = path.replace(/\/+$/, "");
  const idx = clean.lastIndexOf("/");
  if (idx <= 0) return "/";
  return clean.slice(0, idx);
}

function encodeReportPath(absPath) {
  return absPath.split("/").map(encodeURIComponent).join("/");
}

function decodeReportPath(segment) {
  const joined = segment.split("/").map(decodeURIComponent).join("/");
  return joined.startsWith("/") ? joined : `/${joined}`;
}

function normalizeReport(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw.artifact_kind && raw.artifact_kind !== REPORT_KIND) return null;
  const checks = Array.isArray(raw.checks)
    ? raw.checks.map((c) => ({
        id: String((c && c.id) || ""),
        status: String((c && c.status) || ""),
        detail: String((c && c.detail) || ""),
        evidence: Array.isArray(c && c.evidence) ? c.evidence.map(String) : [],
      }))
    : [];
  return {
    design: String(raw.design || ""),
    verdict: String(raw.verdict || ""),
    scope: String(raw.scope || ""),
    system: String(raw.system || ""),
    contractSha256: String(raw.contract_sha256 || ""),
    checks,
  };
}

async function apiGet(host, path) {
  return host.agentServer.request({ path });
}

async function listSubdirs(host, absPath) {
  const items = [];
  let pageId = null;
  for (let i = 0; i < MAX_SUBDIR_PAGES; i += 1) {
    let reqPath = `/api/file/search_subdirs?path=${encodeURIComponent(absPath)}&limit=100`;
    if (pageId) reqPath += `&page_id=${encodeURIComponent(pageId)}`;
    const res = await apiGet(host, reqPath);
    if (res && Array.isArray(res.items)) items.push(...res.items);
    pageId = res && res.next_page_id ? res.next_page_id : null;
    if (!pageId) break;
  }
  return items;
}

async function downloadFile(host, absPath) {
  const res = await apiGet(host, `/api/file/download?path=${encodeURIComponent(absPath)}`);
  if (typeof res === "string") {
    try {
      return JSON.parse(res);
    } catch {
      return res;
    }
  }
  return res;
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const idx = next;
      next += 1;
      try {
        results[idx] = { ok: true, value: await fn(items[idx]) };
      } catch (error) {
        results[idx] = { ok: false, error };
      }
    }
  }
  const workers = [];
  for (let i = 0; i < Math.min(limit, items.length); i += 1) workers.push(worker());
  await Promise.all(workers);
  return results;
}

async function listLocalWorkspaceRoots(host) {
  const roots = new Map();
  const add = (root, label) => {
    if (!root || typeof root !== "string") return;
    const clean = root.replace(/\/+$/, "");
    if (!clean) return;
    const existing = roots.get(clean);
    if (existing) {
      if (!existing.label && label) existing.label = label;
    } else {
      roots.set(clean, { root: clean, label: label || basename(clean) });
    }
  };
  let pageId = null;
  for (let i = 0; i < MAX_CONVERSATION_PAGES; i += 1) {
    let reqPath = "/api/conversations/search?limit=100&sort_order=CREATED_AT_DESC";
    if (pageId) reqPath += `&page_id=${encodeURIComponent(pageId)}`;
    const res = await apiGet(host, reqPath);
    const items = (res && res.items) || [];
    for (const convo of items) {
      const ws = convo && convo.workspace;
      if (ws && ws.kind === "LocalWorkspace" && typeof ws.working_dir === "string") {
        add(ws.working_dir, convo.title || convo.id);
      }
    }
    pageId = res && res.next_page_id ? res.next_page_id : null;
    if (!pageId) break;
  }
  try {
    const res = await apiGet(host, "/api/workspaces");
    const workspaces = (res && res.workspaces) || [];
    for (const ws of workspaces) {
      if (ws && typeof ws.path === "string") add(ws.path, ws.name || null);
    }
  } catch {
    // /api/workspaces is a convenience source only; conversations suffice.
  }
  return [...roots.values()];
}

async function findOutDirs(host, root) {
  const outDirs = [];
  const queue = [{ dir: root, depth: 0 }];
  let scanned = 0;
  while (queue.length && scanned < MAX_DIRS_PER_WORKSPACE) {
    const { dir, depth } = queue.shift();
    scanned += 1;
    let subs;
    try {
      subs = await listSubdirs(host, dir);
    } catch {
      continue; // unreadable directory — skip, do not fail the scan
    }
    for (const sub of subs) {
      if (!sub || typeof sub.name !== "string" || typeof sub.path !== "string") continue;
      if (sub.name === "out") {
        outDirs.push(sub.path);
      } else if (depth + 1 < MAX_SCAN_DEPTH && !SKIP_DIRS.has(sub.name)) {
        queue.push({ dir: sub.path, depth: depth + 1 });
      }
    }
  }
  return outDirs;
}

async function scanWorkspace(host, workspace) {
  const outDirs = await findOutDirs(host, workspace.root);
  const probes = [];
  const seen = new Set();
  for (const outDir of outDirs) {
    let designDirs = [];
    try {
      designDirs = await listSubdirs(host, outDir);
    } catch {
      designDirs = [];
    }
    const hasAppDir = new Set(
      designDirs.filter((d) => d && typeof d.name === "string").map((d) => d.name),
    );
    const candidates = new Set(hasAppDir);
    const contractDirName = basename(dirname(outDir));
    if (contractDirName) candidates.add(contractDirName);
    for (const design of candidates) {
      const reportPath = `${outDir}/${design}${REPORT_SUFFIX}`;
      if (seen.has(reportPath)) continue;
      seen.add(reportPath);
      probes.push({ design, outDir, reportPath, hasApp: hasAppDir.has(design) });
    }
  }
  const results = await mapLimit(probes, FETCH_CONCURRENCY, async (probe) => {
    try {
      const raw = await downloadFile(host, probe.reportPath);
      return { ...probe, report: normalizeReport(raw) };
    } catch (error) {
      if (isNotFound(error)) return { ...probe, report: null };
      throw error;
    }
  });
  const entries = [];
  for (const result of results) {
    if (!result.ok) continue; // permission errors etc. — skip the artifact
    const probe = result.value;
    if (probe.report || probe.hasApp) {
      entries.push({
        design: probe.design,
        workspace,
        outDir: probe.outDir,
        reportPath: probe.report ? probe.reportPath : null,
        report: probe.report,
        hasApp: probe.hasApp,
      });
    }
  }
  return entries;
}

function verdictBadge(verdict) {
  const kind = verdict === "pass" ? "ok" : verdict === "fail" ? "bad" : "dim";
  return el("span", `dbr-badge dbr-badge-${kind}`, verdict || "unknown");
}

function checksSummary(report) {
  const counts = { pass: 0, fail: 0, not_applicable: 0, other: 0 };
  for (const check of report.checks) {
    if (check.status in counts) counts[check.status] += 1;
    else counts.other += 1;
  }
  const parts = [];
  if (counts.pass) parts.push(`${counts.pass} pass`);
  if (counts.fail) parts.push(`${counts.fail} fail`);
  if (counts.not_applicable) parts.push(`${counts.not_applicable} n/a`);
  if (counts.other) parts.push(`${counts.other} other`);
  return parts.join(", ") || "no checks";
}

async function renderList(host, root, navigate, disposed) {
  const head = el("div", "dbr-head");
  head.append(el("h1", "dbr-title", "Dashboard reports"));
  head.append(
    el(
      "p",
      "dbr-sub",
      "Dashboard gate reports and generated app artifacts found under `out/` in local workspaces on this Agent Server.",
    ),
  );
  const rescan = el("button", "dbr-btn", "Rescan");
  rescan.type = "button";
  head.append(rescan);
  root.append(head);

  const status = el("p", "dbr-status", "Scanning workspaces…");
  root.append(status);
  const tableWrap = el("div");
  root.append(tableWrap);

  let generation = 0;
  async function scan() {
    const gen = (generation += 1);
    status.className = "dbr-status";
    status.textContent = "Scanning workspaces…";
    tableWrap.textContent = "";
    rescan.disabled = true;

    let workspaces = [];
    try {
      workspaces = await listLocalWorkspaceRoots(host);
    } catch (error) {
      if (!disposed() && generation === gen) {
        status.className = "dbr-status dbr-error";
        status.textContent = `Could not list conversations: ${msg(error)}`;
        rescan.disabled = false;
      }
      return;
    }

    const entries = [];
    let skipped = 0;
    for (const workspace of workspaces) {
      if (disposed() || generation !== gen) return;
      try {
        entries.push(...(await scanWorkspace(host, workspace)));
      } catch {
        skipped += 1; // workspace unreadable — continue with the rest
      }
    }
    if (disposed() || generation !== gen) return;

    entries.sort(
      (a, b) => a.design.localeCompare(b.design) || a.outDir.localeCompare(b.outDir),
    );
    rescan.disabled = false;

    if (!entries.length) {
      status.textContent = workspaces.length
        ? "No dashboard artifacts found in local workspaces."
        : "No local workspaces found on this Agent Server.";
      return;
    }

    status.textContent =
      `${entries.length} artifact${entries.length === 1 ? "" : "s"} across ` +
      `${workspaces.length} workspace${workspaces.length === 1 ? "" : "s"}` +
      (skipped ? ` (${skipped} unreadable skipped)` : "");

    const table = el("table", "dbr-table");
    const thead = el("thead");
    const hrow = el("tr");
    for (const label of ["Design", "Verdict", "Checks", "Artifacts", "Workspace"]) {
      hrow.append(el("th", "dbr-th", label));
    }
    thead.append(hrow);
    table.append(thead);

    const tbody = el("tbody");
    for (const entry of entries) {
      const row = el("tr", "dbr-tr");

      const nameTd = el("td", "dbr-td");
      if (entry.reportPath) {
        const link = el("button", "dbr-link", entry.design);
        link.type = "button";
        link.addEventListener("click", () =>
          navigate(`${EXT_ROOT}/view/${encodeReportPath(entry.reportPath)}`),
        );
        nameTd.append(link);
      } else {
        nameTd.append(document.createTextNode(entry.design));
      }
      row.append(nameTd);

      const verdictTd = el("td", "dbr-td");
      if (entry.report) verdictTd.append(verdictBadge(entry.report.verdict));
      else verdictTd.append(el("span", "dbr-badge dbr-badge-dim", "no report"));
      row.append(verdictTd);

      row.append(
        el("td", "dbr-td", entry.report ? checksSummary(entry.report) : "—"),
      );

      const artifactsTd = el("td", "dbr-td");
      const artifacts = [];
      if (entry.report) artifacts.push("report");
      if (entry.hasApp) artifacts.push("generated app");
      artifactsTd.append(el("span", "dbr-path", artifacts.join(" + ")));
      if (entry.reportPath) {
        artifactsTd.append(document.createTextNode(" "));
        artifactsTd.append(el("div", "dbr-path", entry.outDir));
      }
      row.append(artifactsTd);

      const wsTd = el("td", "dbr-td");
      wsTd.append(el("div", null, entry.workspace.label));
      wsTd.append(el("div", "dbr-path", entry.workspace.root));
      row.append(wsTd);

      tbody.append(row);
    }
    table.append(tbody);
    tableWrap.append(table);
  }

  rescan.addEventListener("click", () => {
    void scan();
  });
  await scan();
}

async function renderDetail(host, root, absPath, navigate, disposed) {
  const head = el("div", "dbr-head");
  const back = el("button", "dbr-btn", "← Reports");
  back.type = "button";
  back.addEventListener("click", () => navigate(EXT_ROOT));
  head.append(back);
  head.append(
    el("h1", "dbr-title", basename(absPath).replace(/\.dash-report\.json$/, "")),
  );
  head.append(el("p", "dbr-sub dbr-mono", absPath));
  root.append(head);

  const status = el("p", "dbr-status", "Loading report…");
  root.append(status);

  let raw;
  try {
    raw = await downloadFile(host, absPath);
  } catch (error) {
    if (!disposed()) {
      status.className = "dbr-status dbr-error";
      status.textContent = `Could not load report: ${msg(error)}`;
    }
    return;
  }
  if (disposed()) return;

  const report = normalizeReport(raw);
  if (!report) {
    status.className = "dbr-status dbr-error";
    status.textContent = "File is not a dashboard gate report.";
    return;
  }
  status.remove();

  const bannerKind =
    report.verdict === "pass"
      ? "dbr-verdict-pass"
      : report.verdict === "fail"
        ? "dbr-verdict-fail"
        : "dbr-verdict-other";
  root.append(
    el(
      "div",
      `dbr-verdict-banner ${bannerKind}`,
      `Verdict: ${report.verdict || "unknown"} — ${checksSummary(report)}`,
    ),
  );

  const meta = el("dl", "dbr-meta");
  const metaRows = [
    ["Design", report.design || "—"],
    ["Scope", report.scope || "—"],
    ["System", report.system || "—"],
    ["Contract SHA-256", report.contractSha256 || "—"],
  ];
  for (const [key, value] of metaRows) {
    meta.append(el("dt", null, key));
    meta.append(el("dd", "dbr-mono", value));
  }
  const metaPanel = el("div", "dbr-panel");
  metaPanel.append(meta);
  root.append(metaPanel);

  if (report.checks.length) {
    const table = el("table", "dbr-table");
    const thead = el("thead");
    const hrow = el("tr");
    for (const label of ["Check", "Status", "Detail"]) {
      hrow.append(el("th", "dbr-th", label));
    }
    thead.append(hrow);
    table.append(thead);
    const tbody = el("tbody");
    for (const check of report.checks) {
      const row = el("tr", "dbr-tr");
      row.append(el("td", "dbr-td dbr-mono", check.id));
      const statusTd = el("td", "dbr-td dbr-check-status");
      const kind =
        check.status === "pass"
          ? "ok"
          : check.status === "fail"
            ? "bad"
            : "dim";
      statusTd.append(el("span", `dbr-badge dbr-badge-${kind}`, check.status));
      row.append(statusTd);
      const detailTd = el("td", "dbr-td");
      detailTd.append(el("div", "dbr-detail", check.detail || "—"));
      if (check.evidence.length) {
        const list = el("ul", "dbr-evidence");
        for (const item of check.evidence) list.append(el("li", null, item));
        detailTd.append(list);
      }
      row.append(detailTd);
      tbody.append(row);
    }
    table.append(tbody);
    root.append(table);
  } else {
    root.append(el("p", "dbr-warn", "Report contains no checks."));
  }

  const markdownPath = absPath.replace(/\.json$/, ".md");
  try {
    const markdown = await downloadFile(host, markdownPath);
    if (!disposed() && typeof markdown === "string") {
      const details = el("details", "dbr-details");
      details.append(el("summary", null, "Markdown report"));
      details.append(el("pre", "dbr-pre", markdown));
      root.append(details);
    }
  } catch {
    // The sibling .md projection is optional.
  }
  if (disposed()) return;

  const details = el("details", "dbr-details");
  details.append(el("summary", null, "Raw JSON"));
  details.append(el("pre", "dbr-pre", JSON.stringify(raw, null, 2)));
  root.append(details);
}

function mountPage(host, context) {
  let disposed = false;
  const isDisposed = () => disposed;

  const root = el("section", "dbr");
  const style = el("style");
  style.textContent = STYLES;
  root.append(style);
  context.container.append(root);

  const path = context.path || "";
  if (path === "") {
    void renderList(host, root, context.navigate, isDisposed);
  } else if (path === "view" || path.startsWith("view/")) {
    const segment = path.slice("view".length).replace(/^\/+/, "");
    if (!segment) {
      context.navigate(EXT_ROOT);
    } else {
      void renderDetail(host, root, decodeReportPath(segment), context.navigate, isDisposed);
    }
  } else {
    void renderList(host, root, context.navigate, isDisposed);
  }

  return () => {
    disposed = true;
    root.remove();
  };
}

export function activate(host) {
  if (host.apiVersion !== "1") {
    throw new Error("dashboard-reports requires Canvas host API 1.");
  }
  return host.registerPage(PAGE_ID, (context) => mountPage(host, context));
}

// Exposed for the repository's node:test suite; not part of the host API.
export const __internals = {
  basename,
  checksSummary,
  decodeReportPath,
  dirname,
  encodeReportPath,
  normalizeReport,
};
