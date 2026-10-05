# Contracts and serialized artifacts

JSON contracts/models are strict and immutable unless noted. Generated files
are projections; edit the source contract and regenerate instead of changing
them manually.

## DashboardContract v1

Top-level fields: `schema_version: 1`, `system: "dashboard"`,
`artifact_kind: "dashboard_contract"`, slug `name`, non-empty `description`,
`device`, `protocol`, non-empty `transports`, non-empty `platforms`, non-empty
`widgets`, optional/defaulted `session`, optional `shell`, `wasm`, and
`webmcp`, and default-empty `imports`.

| Model | Fields and invariants |
| --- | --- |
| `Device` | Optional `firmware_contract` and `firmware_sha256` must be set together; digest is 64 lowercase hex characters. Relative firmware paths resolve from the `.dash.json` file; absolute paths pass through unchanged. |
| `Protocol` | `framing: "cobs-crc16"`, `max_frame_bytes` 16–512, and at least one `Message`. |
| `Message` | ID 0–254 (255 is reserved for ACK frames), snake-case name, `device_to_host` or `host_to_device`, `ack` default false, and typed `fields`. `ack=true` is valid only for host-to-device messages. |
| `FieldSpec` | Snake-case `name`; type `u8`, `i8`, `u16`, `i16`, `u32`, `i32`, `f32`, or `bool`; optional `unit`, positive finite `scale`, optional min/max. Gate checks require min < max and limits within the scaled wire type. |
| `Transport` | Discriminated union by `kind`: `web_bluetooth`, `tauri_ble`, `webusb`, `web_serial`, `tauri_serial`, `websocket`, or `webrtc`. Transport IDs are slug names. BLE UUID values are lowercase canonical 128-bit or `0x` 16-bit values; serial baud rate must be one of the supported standard rates from 9600 through 3,000,000. |
| `WebBluetoothTransport`, `TauriBleTransport` | `id`, `kind`, `service_uuid`, `rx_characteristic`, `tx_characteristic`, optional `name_prefix`. |
| `WebUsbTransport` | `id`, `kind`, 16-bit `vendor_id`, optional 16-bit `product_id`, 8-bit `interface_class` (the gate requires vendor-specific `0xff`) and `interface_number`, and nonzero 8-bit IN/OUT endpoints. |
| `WebSerialTransport`, `TauriSerialTransport` | `id`, `kind`, supported `baud_rate`, optional USB vendor/product IDs and Bluetooth service class ID. |
| `WebSocketTransport` | `id`, `kind`, non-empty `url`, optional `subprotocol`. The gate requires `wss://`, except loopback `ws://` development URLs. |
| `WebRtcTransport` | `id`, `kind`, non-empty `signaling_url` (the gate requires `wss://`), `data_channel` default `dash`, `ordered` default true, and an optional `ice_servers` list (default empty; each `IceServer.urls` list is non-empty and uses `stun:`, `turn:`, or `turns:`). Signaling uses the dashboard offerer JSON protocol. |
| `Route` | Browser plus a declared transport ID and `acknowledged_caveats`. |
| `PlatformDecl` | OS, status `supported` or `unsupported`, routes, optional reason. Supported declarations require routes and no reason; unsupported declarations require a reason and no routes. |
| `Widget` | Slug `id`; kind `value`, `gauge`, `chart`, `indicator`, `button`, `toggle`, or `slider`; non-empty `label`; optional telemetry `source`, command and field; `hazard` and `confirm` booleans. Display widgets use device-to-host `message.field`; controls use host-to-device commands. Hazardous controls require `confirm=true`. |
| `SessionConfig` | `connect_timeout_ms` default 10,000 (range 1,000–60,000), `ack_timeout_ms` default 1,000 (50–10,000), and `reconnect`. |
| `Reconnect` | `max_attempts` default 5 (0–20), `backoff_ms` default 1,000 (100–60,000). |
| `ShellConfig` / `TauriShellConfig` | Optional `tauri` object with non-empty `identifier` and `product_name`, semantic `version`, and a non-empty unique target list from `windows`, `macos`, `linux`, `android`, `ios`. The `tauri.identifier` gate requires reverse-DNS style. iPadOS routes map to the iOS target. |
| `WasmConfig` / `WasmModule` | Optional module list; each module has a slug `id`, one or more source paths, and one or more exported symbols. |
| `WebMcpConfig` | Optional settings: `enabled` defaults true, `expose_controls` defaults false, optional `origin_trial_token`. |
| `ImportRef` | `from_system` is one of `firmware`, `circuit`, `ux-creator`, `mech`, `wire`, `bard`, `fpga`, `sim`, `prodeng`, `doc`; non-empty copied-artifact path and lowercase SHA-256. Relative paths resolve from the `.dash.json` file; absolute paths pass through unchanged. |

OS literals are `windows`, `macos`, `linux`, `bsd`, `chromeos`, `android`,
`ios`, and `ipados`. Browser literals are `chrome`, `edge`, `opera`,
`samsung_internet`, `firefox`, `safari`, `bluefy`, and `tauri`. Transport
routes and caveats are enumerated in the matrix tool; unknown pairs are not
implicit support.

Supported serial baud rates are 9600, 14400, 19200, 28800, 38400, 57600,
115200, 230400, 460800, 921600, 1000000, 1500000, 2000000, and 3000000.

Wire field sizes are: `u8`/`i8`/`bool` 1 byte; `u16`/`i16` 2 bytes; `u32`,
`i32`, and `f32` 4 bytes. The frame-size gate accounts for message ID,
sequence, payload, CRC, COBS overhead, and the zero delimiter.

## GateReport and Check

`Check` has `id`, `status` (`pass`, `fail`, `not_applicable`), `detail`
(default empty string), and `evidence: string[]` (default empty list).
`GateReport` has system
`dashboard`, artifact kind `dashboard_gate_report`, design, scope (`static` or
`full`), nullable `contract_sha256`, verdict (`pass` or `fail`), and ordered
checks. The report fails if any check fails; `not_applicable` is not a failure.
An unreadable/invalid contract is returned as a failed `contract.schema`
check.

Static check IDs are:

```text
contract.schema
protocol.ids-unique         protocol.names-unique       protocol.frame-size
protocol.field-range        protocol.ack-direction
transport.ids-unique        transport.secure-url        transport.webusb-vendor-class
transport.ble-uuids         transport.used
platform.declared           platform.route-known        platform.caveats-acknowledged
platform.unsupported-reason
tauri.identifier            tauri.targets-routes        tauri.transport-requires-shell
widget.refs                 widget.hazard-confirm       widget.ids-unique
imports.sha256              firmware.link
webmcp.tool-names           webmcp.hazard-consequential webmcp.schema
```

When WebMCP is not configured, its three checks are `not_applicable`.

Full checks add `generated.fresh`, `runtime.typecheck`, `runtime.test`,
`wasm.parity`, `wasm.modules`, `e2e.chromium`, `visual.capture`, and
`smoke.servo`. WASM modules are not applicable if none are declared; Servo
smoke is not applicable unless a WebSocket transport exists.

## Generated configuration and manifest

`dashboard.config.json` has `contract_sha256`, `contract`, `routes`, and
`webmcp_tools`. `contract` is the serialized DashboardContract with optional
`shell` excluded. Each `routes[]` entry has `os`, `browser`, `transport`,
`kind`, `support`, `caveats`, and `caveat_text`; tool definitions are the same
WebMCP projection used by the runtime.

The generated web root also contains `index.html`, `dashboard.js`,
`styles.css`, and `favicon.svg`. `manifest.webmanifest` has `name`,
`short_name` (first 12 characters), `start_url: "./"`, `display: "standalone"`,
`background_color: "#101820"`, and `theme_color: "#15252b"`. When WebMCP is
configured, `<name>.dash-webmcp.json` has `schema_version: 1`, `system:
"dashboard"`, `artifact_kind: "dashboard_webmcp_tools"`, `contract_sha256`,
and `tools`. Optional Tauri scaffold files are under `out/<name>/tauri/`.

`dash-manifest.json` is:

```json
{
  "contract_sha256": "lowercase SHA-256 of the source contract",
  "generator_version": "dashboard package version",
  "files": {
    "generated-relative-name": "lowercase SHA-256 of file bytes"
  }
}
```

The `files` mapping is sorted and covers generated projections plus
`dashboard.js`; freshness checks validate the contract hash, containment of
each listed path, file presence, and file hash.

## Protocol export

`<name>.dash-protocol.json` contains `schema_version: 1`, `system:
"dashboard"`, `artifact_kind: "dashboard_protocol"`, `design`,
`contract_sha256`, `framing`, and the serialized `messages`. The companion C
header is `<name>.dash-protocol.h`. These are projections of the same contract
framing and message fields.

## `screens.json`

The Chromium capture writes `<name>.screens/desktop.png`,
`mobile.png`, and `screens.json`. The initial JSON has `browser: "chromium"`,
`browser_version`, and two `viewports` entries. Each entry has `name`,
`browser: "chromium"`, `browser_version`, requested `width`/`height`, relative
`file`, `page_errors`, and `console_errors`. Python validation adds `sha256`
and `bytes` for the image. The top level is enriched with `contract_sha256`
from the manifest and `generated_manifest_sha256`. Required viewports are
desktop 1280×800 and mobile 390×844; full-page image height may exceed the
viewport height.

## DashboardRequest v2

Outbound `<design>.<id>.dash-request.json` has
`schema_version: 2`, `system: "dashboard"`, `artifact_kind: "dash_request"`,
slug `id`, `design`, target (`bard`, `circuit`, `doc`, `firmware`, `fpga`,
`mech`, `prodeng`, `sim`, `wire`, or `ux-creator`), `risk` (`low`/`high`),
`change` and `rationale` (at least 8 characters), optional `failing_checks`,
`contract_sha256`, `inputs: HashedPath[]`, and `decision_refs: string[]`.
Inputs automatically contain the workspace-relative dashboard contract and,
when configured, the linked firmware contract with current SHA-256. High-risk
requests require at least one existing VRP decision event ID.

## SLP v2 requests and responses

Both liaison models are frozen and reject unknown fields. Hashes are 64
lowercase hex characters; request IDs and dependencies match the family SLP v2 id pattern
`^[a-z0-9][a-z0-9._-]{0,63}$`.
All paths must be workspace-relative, without absolute paths, drive prefixes,
backslashes, or `..` traversal.

The shared `HashedPath` model contains a non-empty `path` and `sha256`.
`GateVerdict` contains a non-empty `gate` and `verdict` (`pass`, `fail`, or
`unknown`).

`UxRequest` has `schema_version: 2`, `system: "ux-creator"`, `id`,
`target_agent` (`bard`, `circuit`, `dashboard`, `doc`, `firmware`, `fpga`,
`mech`, `prodeng`, `sim`, `wire`), stage (`requirements`, `design`,
`manufacturing_handoff`, `build`, `evaluation`, `revision`), risk, purpose
(trimmed and at least 20 characters), non-empty rationale, non-empty
`requested_changes` entries, hashed `inputs`, non-empty
`expected_deliverables` and `acceptance` entries, optional `depends_on`, and
aware `created_at`. An ID cannot depend on itself. High-risk requests must
hash a `.ux.json` input; its bound UX contract must be readable and a job ID
from `jobs[].id` must appear as a token in the rationale.

`UxResponse` has `schema_version: 2`, `system: "ux-creator"`, request ID,
responder target, status (`accepted`, `in_progress`, `done`, `rejected`,
`deferred`, `needs_info`), reason, path-to-SHA `input_hashes`, hashed
`artifacts`, `gate_verdicts` (`pass`, `fail`, `unknown`), decision/impression
refs, `questions_for_user`, and aware `responded_at`. Reasons for statuses
other than accepted/in-progress need 20 non-whitespace characters. `done`
requires at least one artifact and gate verdict and may not claim fail/unknown.
The stricter `ux_respond` operation also requires a current full passing report
and validates all claims and referenced records; see
[Sister cooperation](sister-cooperation.md).

`UxRespondInput` contains request ID and status plus optional/default-empty
`reason`, artifact paths, `gate_verdicts`, decision/impression refs,
`questions_for_user`, and optional `liaison_dir`. The input reason is trimmed;
the `UxResponse` applies the minimum-length and `done` constraints.

## VRP v1 records

Records use strict frozen models and append-only JSON Lines under
`observations/dashboard/`. Every envelope has `schema_version: 1`,
`plugin: "dashboard"`, positive `sequence`, SHA-256 `event_id`, and
`recorded_at`.

- **Decision:** `kind: "decision"` plus slug `id` and `stage`, 10+ character
  `question`, non-empty `principles` (each at least 12 characters), at least
  two `options` (`name`, non-empty `pros`, non-empty `cons`), `chosen` naming
  one option, `rationale` (at least 200 characters), `assumptions`, `unknowns`,
  non-empty `risks`, `revisit_when`, `decided_by` (`agent`/`user`), and
  non-empty `evidence`. File evidence is workspace-relative and bound by
  SHA-256; non-file evidence names a standard, datasheet, or law.
- **Stage impression:** `kind: "stage_impression"`, slug `stage`, non-empty
  `artifacts` of hashed workspace files/trees, and `impression` of at least
  400 characters and three distinct sentences.
- **Vision review:** `kind: "vision_review"`, optional `image_path` and
  `image_sha256`, optional `source_event_id`, required `model`, slug
  `checklist`, `findings[]` (`category`, severity `info|warning|error`, and
  `note`), and long-form `impression`. Input must bind either an image or
  source event.

For all three record kinds, the envelope fields are `schema_version: 1`,
`plugin: "dashboard"`, `sequence` (starting at 1), SHA-256 `event_id`,
UTC `recorded_at`, and `kind`. The event ID is the SHA-256 of compact,
key-sorted JSON containing the kind, sequence, and record body. Decision file
evidence is converted to `{path, sha256}` by the writer; a non-file reference
is `{reference}`. Impression artifact paths are converted to `{path, sha256}`.
Vision input image paths are hashed from image bytes; the stored record
contains `image_sha256` and an image or source-event binding.

Writers append to `decisions.jsonl`, `impressions.jsonl`, and
`vision-reviews.jsonl`. Directory hashes use sorted relative paths and file
hashes while skipping `.git`, `.venv`, `node_modules`, `__pycache__`, and
`.pytest_cache`.

The informational `dashboard_records_status` result has `verdict: "pass"`,
`records_dir`, counts by `decision`, `stage_impression`, and `vision_review`,
and `last_stop` (parsed Stop-hook status or `null`). The status file itself
has `plugin`, `session_id`, epoch-seconds `checked_at`, `verdict` (`pass` or
`fail`), and `problems[]`.

## `records-policy.json`

Policy schema v1 names plugin `dashboard`, directory
`observations/dashboard`, artifact globs:

```text
**/*.dash.json
**/*.dash-report.json
**/*.dash-report.md
**/*.dash-protocol.json
**/*.dash-protocol.h
**/dash-manifest.json
**/*.screens/*.png
**/servo.png
**/*.dash-request.json
**/liaison/*.ux-response.json
```

It ignores `examples/**`, `tests/**`, `.devin/**`, and `runtime/**`, permits
two Stop denials, and instructs agents to use the three VRP MCP tools or
`python -m dashboard record decision|impression|vision-review --json <file>`.
Impressions must be 400+ characters and three sentences about observations,
what works/raises concern, user interpretation, and next action.
