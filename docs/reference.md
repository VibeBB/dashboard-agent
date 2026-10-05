# Public function and CLI reference

This index covers public module-level functions and public model validator
methods defined in `src/dashboard/*.py`. Private helpers beginning with `_`
and imported third-party functions are intentionally omitted.

## Python functions

| Module and function | Arguments | Purpose |
| --- | --- | --- |
| `cli.main` | `argv: Sequence[str] \| None = None` | Parse a dashboard CLI invocation, call the service layer, and return its process status. |
| `contract.load_contract` | `path: str \| Path` | Load and validate a DashboardContract JSON file. |
| `contract.resolve` | `contract_path: str \| Path, relative: str` | Resolve a contract-relative file reference. |
| `doctor.checks` | none | Probe required and optional local dashboard tools. |
| `gates.check_contract` | `contract: DashboardContract, contract_path: Path` | Run deterministic static checks against a parsed contract and its source path. |
| `gates.generated_freshness` | `contract_path: Path, generated_dir: Path` | Compare the generated manifest and artifact hashes with current files. |
| `gates.run_gates` | `contract_path: Path, out_dir: Path, *, full: bool = False` | Produce a static or full deterministic GateReport. |
| `gates.report_markdown` | `report: GateReport` | Render a GateReport as Markdown. |
| `gates.write_outputs` | `report: GateReport, out_dir: Path` | Write JSON and Markdown report files. |
| `generate.manifest_file_hashes` | `output: Path, names: Iterable[str]` | Compute hashes for generated files, including the bundled `dashboard.js`. |
| `generate.write_artifacts` | `output: Path, artifacts: Mapping[str, bytes], previous_names: Iterable[str]` | Safely write current generated projections and remove stale manifest-listed files. |
| `generate.build_config` | `contract: DashboardContract, contract_sha256: str` | Build runtime configuration, resolved routes, caveats, and WebMCP definitions. |
| `generate.build_tauri_scaffold` | `contract: DashboardContract` | Build optional Tauri v2 scaffold files for a contract shell declaration. |
| `generate.generate` | `contract_path: Path, out_root: Path` | Generate an application and return its output directory and written paths. |
| `interchange.sha256_file` | `path: Path` | Hash a file's bytes with SHA-256. |
| `liaison.ux_inbox` | `root: Path \| None = None, liaison_dir: Path \| None = None` | Validate and summarize UX liaison requests, replies, dependencies, and stale inputs. |
| `liaison.ux_respond` | `payload: Mapping[str, object], root: Path \| None = None` | Validate and atomically write a dashboard response to a UX request. |
| `matrix.private_network_caveat` | `url: str` | Return the local-network caveat for private/link-local/`.local` endpoints. |
| `matrix.route_caveats` | `os_name: OSName, browser: BrowserName, kind: TransportKind, url: str \| None` | Return all caveats that apply to one route. |
| `matrix.route_support` | `os_name: OSName, browser: BrowserName, kind: TransportKind` | Look up support status and optional caveat for one browser route. |
| `mcp_server.tool_specs` | none | Construct MCP Tool objects, schemas, and read-only annotations. |
| `mcp_server.list_tools` | none (async) | Return the available MCP tools. |
| `mcp_server.dispatch` | `name: str, arguments: dict[str, object]` | Dispatch one MCP tool to the shared service layer. |
| `mcp_server.render_content` | `payload: service.Json` | Render JSON plus bounded inline image content for image tools. |
| `mcp_server.call_tool` | `name: str, arguments: dict[str, object]` | Execute an MCP tool and build its text/image result and error flag. |
| `mcp_server.main` | none | Run the stdio MCP server. |
| `protocol.protocol_export` | `contract: DashboardContract, contract_sha256: str` | Build the versioned dashboard protocol interchange object. |
| `records.sentence_count` | `text: str` | Count supported Latin and CJK sentence terminators. |
| `records.impression_is_prose` | `value: str` | Validate and return a distinct, long-form stage/vision impression. |
| `records.sha256_file` | `path: Path` | Hash a file for a VRP record. |
| `records.tree_sha256` | `path: Path` | Hash a file or a stable, sorted directory-tree listing. |
| `records.records_dir` | `root: Path \| None = None` | Resolve the workspace's `observations/dashboard` directory. |
| `records.record_decision` | `payload: Mapping[str, Any], root: Path \| None = None` | Validate, hash evidence, and append a decision event. |
| `records.record_impression` | `payload: Mapping[str, Any], root: Path \| None = None` | Hash artifacts and append a stage-impression event. |
| `records.record_vision_review` | `payload: Mapping[str, Any], root: Path \| None = None` | Bind an advisory review to image bytes or a source event and append it. |
| `records.records_summary` | `root: Path \| None = None` | Return VRP log counts and the last Stop-hook status. |
| `report.write_outputs` | `report: GateReport, out_dir: Path` | Delegate to the gate report writer. |
| `requests.write_request` | `contract_path: Path, design: str, out_dir: Path, *, target: str, risk: str, change: str, rationale: str, failing_checks: list[str], decision_refs: list[str]` | Create and write an outbound DashboardRequest v2 bound to contract/firmware inputs. |
| `screenshots.capture` | `generated_dir: Path, out_dir: Path, *, timeout: int = 180` | Capture and validate desktop/mobile Chromium screenshots and `screens.json`. |
| `service.doctor_payload` | none | Return toolchain probe results as JSON. |
| `service.validate_payload` | `contract_path: Path` | Return contract validation status and a small design summary. |
| `service.generate_payload` | `contract_path: Path, out_dir: Path \| None = None` | Generate the application and return paths or a structured failure. |
| `service.gates_payload` | `contract_path: Path, out_dir: Path \| None = None, *, full: bool = False` | Run gates, write reports, and add full-gate image/vision metadata. |
| `service.matrix_payload` | none | Return all implemented support rows and caveats. |
| `service.protocol_export_payload` | `contract_path: Path, out_dir: Path \| None = None` | Write the protocol JSON interchange artifact. |
| `service.smoke_payload` | `contract_path: Path, out_dir: Path \| None = None` | Run Servo smoke and return any screenshot/vision metadata. |
| `service.screenshot_payload` | `contract_path: Path, out_dir: Path \| None = None` | Require fresh output, capture screenshots, and return hashes and image hints. |
| `service.request_payload` | `contract_path: Path, out_dir: Path \| None, *, target: str, risk: str, change: str, rationale: str, failing_checks: list[str], decision_refs: list[str]` | Write a sister request and return the versioned object plus bound hashes. |
| `service.ux_inbox_payload` | `liaison_dir: Path \| None = None` | Return the validated UX inbox state. |
| `service.ux_respond_payload` | `payload: Mapping[str, object]` | Return a validated SLP response result. |
| `service.record_payload` | `kind: str, payload: Mapping[str, object]` | Route a VRP writer and return its record result. |
| `service.records_status_payload` | none | Return VRP record counts and last Stop-hook result. |
| `servo.save_screenshot` | `base: str, app: Path` | Save a Servo WebDriver PNG where the browser supports screenshot capture. |
| `servo.smoke` | `generated_dir: Path` | Run the bounded Servo WebDriver smoke check with one transient retry when applicable. |
| `wasm.build_codec_parity` | `root: Path, output: Path` | Build the C codec with Emscripten and compare runtime parity in Node. |
| `wasm.build_module` | `root: Path, output: Path, sources: list[Path], exports: list[str]` | Build one declared C module and verify its exports. |
| `webmcp.definitions` | `contract: DashboardContract` | Build WebMCP status/telemetry and optional command definitions. |
| `webmcp.has_hazard` | `contract: DashboardContract, command: str` | Determine whether a host command is exposed by a hazardous widget. |
| `webmcp.json_schema_valid` | `value: object` | Validate the generated JSON Schema subset. |
| `workspace.workspace_root` | none | Resolve the active OpenHands/project workspace root. |
| `workspace.workspace_path` | `value: str \| Path, root: Path \| None = None` | Resolve a workspace-relative path and reject escapes. |

### Public model validators

| Model method | Arguments | Purpose |
| --- | --- | --- |
| `Message.validate_ack_direction` | `self` | Restrict `ack=true` to host-to-device messages. |
| `BleTransportBase.validate_uuid` | `cls, value: str` | Restrict BLE identifiers to lowercase canonical 128-bit or `0x` 16-bit forms. |
| `SerialTransportBase.validate_baud_rate` | `cls, value: int` | Require a supported standard baud rate. |
| `PlatformDecl.validate_status` | `self` | Require routes/no reason for supported platforms and a reason/no routes for unsupported platforms. |
| `TauriShellConfig.validate_targets_unique` | `self` | Reject duplicate Tauri targets. |
| `Device.validate_firmware_pair` | `self` | Require firmware path and SHA-256 to be set together. |
| `HashedPath.validate_workspace_relative_path` | `cls, value: str` | Reject absolute, Windows-drive, backslash, or traversal paths. |
| `UxRequest.validate_request` | `self` | Reject self-dependencies and require a bound UX contract for high-risk requests. |
| `UxResponse.validate_input_hash_paths` | `cls, value: dict[str, str]` | Validate paths used as response input-hash keys. |
| `UxResponse.strip_reason` | `cls, value: str` | Trim response reason whitespace. |
| `UxResponse.validate_response` | `self` | Enforce response reason and `done` artifact/gate requirements. |
| `UxRespondInput.strip_reason` | `cls, value: str` | Trim submitted response reason whitespace. |
| `DashboardRequest.validate_high_risk_refs` | `self` | Require a decision reference for high-risk outbound requests. |

## CLI subcommands

Top-level command names and arguments are from `python -m dashboard --help`
and each subcommand's help:

| Subcommand | Arguments | Purpose |
| --- | --- | --- |
| `doctor` | none | Probe local tool versions. |
| `matrix` | none | Print the browser/OS/transport support matrix. |
| `validate` | `contract` | Validate one contract without generating output. |
| `generate` | `contract [--out DIR]` | Generate the app, protocol projections, and optional Tauri scaffold. |
| `check` | `contract [--out DIR]` | Run static gates and write the report. |
| `gates` | `contract [--out DIR]` | Run full gates and write the report. |
| `smoke` | `contract [--out DIR]` | Run a Servo smoke check. |
| `screenshot` | `contract [--out DIR]` | Capture screenshots from fresh generated output. |
| `protocol-export` | `contract [--out DIR]` | Write protocol interchange JSON. |
| `request` | `contract --target TARGET --risk {low,high} --change TEXT --rationale TEXT [--failing-check ID]... [--decision-ref ID]... [--out DIR]` | Write a DashboardRequest v2. Targets: `bard`, `circuit`, `doc`, `firmware`, `fpga`, `mech`, `prodeng`, `sim`, `wire`, `ux-creator`. |
| `ux-inbox` | `[--liaison-dir DIR]` | Summarize dashboard-targeted SLP v2 requests. |
| `ux-respond` | `--json FILE` | Read an SLP response input object and write a validated response. |
| `record decision` | `--json FILE` | Append a VRP decision. |
| `record impression` | `--json FILE` | Append a VRP stage impression. |
| `record vision-review` | `--json FILE` | Append a VRP vision review. |
| `record status` | optional `--json` is parsed but not used | Show record counts and last Stop-hook verdict. |

CLI output is JSON. `_emit` returns exit code 0 for `verdict=pass` and 1
otherwise; argument-parse errors use argparse's nonzero exit.
