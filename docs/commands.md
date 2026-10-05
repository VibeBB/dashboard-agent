# Slash commands

`plugins/dashboard/commands/` defines six commands. These are concise
OpenHands instructions, not separate argument parsers; the contract or output
directory is supplied in the conversation and then passed to the underlying
dashboard CLI/MCP tool.

| Command | Prompt input | CLI arguments | Behavior |
| --- | --- | --- | --- |
| `/dashboard:design` | Device/product brief and a contract path or requested output location. | `validate <contract>` then `check <contract>`; both take a positional contract path. | Delegates contract authoring to `dashboard-architect`; validates protocol, routes, caveats, widgets, and imports, and reports static-gate failures. |
| `/dashboard:doctor` | No required argument. | `doctor` | Probes the pinned development/full-gate toolchain and reports missing or mismatched tools and image availability. |
| `/dashboard:gates` | Contract path; optionally request static or full gates. | `check <contract> [--out DIR]` or `gates <contract> [--out DIR]`; screenshot may use `screenshot <contract> [--out DIR]`. | Runs static checks or the full runtime/browser/WASM/Servo set and reports artifacts; may capture screenshots for advisory review. |
| `/dashboard:generate` | Contract path. | `generate <contract> [--out DIR]` | Generates the app and protocol projections; reviews the manifest/config and optional scaffold README; never edits generated files manually. |
| `/dashboard:screenshot` | Contract path after generation. | `screenshot <contract> [--out DIR]` | Requires fresh generated output; captures deterministic desktop/mobile Chromium PNGs for advisory visual review. |
| `/dashboard:smoke` | Contract path after generation. | `smoke <contract> [--out DIR]` | Runs the Servo WebDriver smoke check and preserves its assertions; a screenshot failure does not change the smoke verdict. |

All six commands allow `terminal`; `design` also allows `file_editor`.
The command definitions live in `plugins/dashboard/commands/{design,doctor,
gates,generate,screenshot,smoke}.md`.
