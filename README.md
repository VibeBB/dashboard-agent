# dashboard-agent

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/dashboard-agent)

VibeBB's OpenHands plugin for connected-device dashboard developers. A JSON
contract declares device routes and controls.

## Quick start

```bash
uv sync --locked
uv run python -m dashboard validate examples/smart-kettle/smart-kettle.dash.json
uv run python -m dashboard generate examples/smart-kettle/smart-kettle.dash.json
uv run python -m dashboard check examples/smart-kettle/smart-kettle.dash.json
```

Serve `examples/smart-kettle/out/smart-kettle/` from HTTPS or localhost.
Hardware APIs require a user gesture; device selection stays with the user.

## Platform support

The matrix lists routes available to each browser and operating system.
Contracts declare `ios` and `ipados` independently; see both examples.

| OS | Browsers | Usable transports | Caveats |
| --- | --- | --- | --- |
| Windows | Chrome, Edge, Opera (all five); Firefox (network only); Tauri v2 | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel; Tauri native BLE and serial | A WebUSB interface may be claimed by an OS driver. |
| macOS | Chrome, Edge, Opera (all five); Safari and Firefox (network only); Tauri v2 | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel; Tauri native BLE and serial | A WebUSB interface may be claimed by an OS driver. |
| Linux | Chrome, Edge, Opera (all five); Firefox (network only); Tauri v2 | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel; Tauri native BLE and serial | Web Bluetooth needs a Chromium flag and BlueZ; WebRTC in Tauri depends on the WebKitGTK build; a WebUSB interface may be claimed by an OS driver. |
| BSD | BSD Chromium ports and Firefox (network only) | WebSocket, WebRTC DataChannel | Web Bluetooth is disabled; Web Serial is not built; FreeBSD/NetBSD WebUSB is fake-only. OpenBSD compiles a libusb backend, but it is unverified and not offered. WebMCP needs Chromium's testing/origin-trial feature. [Details](docs/research/bsd-chromium.md). |
| ChromeOS | Chrome, Edge, Opera (all five) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | WebUSB may need an interface not claimed by an OS driver. Managed Chromebooks may restrict device APIs; check your admin policy. |
| iOS | Safari, Chrome, Edge, Firefox (WebKit; network only); Bluefy (network and Web Bluetooth); Tauri v2 | WebSocket, WebRTC DataChannel; Bluefy Web Bluetooth; Tauri native BLE | Tauri serial is not supported on iOS; Bluefy notifications can be unreliable. |
| iPadOS | Safari, Chrome, Edge, Firefox (WebKit; network only); Bluefy (network and Web Bluetooth); Tauri v2 | WebSocket, WebRTC DataChannel; Bluefy Web Bluetooth; Tauri native BLE | No WebUSB or Web Serial routes; Tauri serial is not supported. Bluefy notifications can be unreliable. |
| Android | Chrome, Edge, Opera (all five); Firefox and Samsung Internet (network only); Tauri v2 | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel; Tauri native BLE and serial | Android WebUSB and Web Serial have device-driver and support limitations. |

### Native shell (Tauri v2)

The `tauri` route uses native BLE on Windows, macOS, Linux, Android, iOS, and
iPadOS; native serial is available on Windows, macOS, Linux, and Android.
Tauri's iOS target covers iPadOS. Native routes use an in-page picker and
require an explicit connection click. WebSocket and WebRTC remain webview
routes. `dashboard generate` adds `out/<name>/tauri/` only when the contract
declares `shell.tauri`. Run the generated app with:

```bash
cd examples/smart-kettle/out/smart-kettle/tauri
npm install
npx tauri dev
```

The scaffold README covers desktop and mobile builds and OS prerequisites.
WebMCP never exposes device selection or connection tools.

## Transports

The runtime supports Web Bluetooth, WebUSB, Web Serial, native Tauri BLE and
serial, WebSocket, and WebRTC DataChannel. Private, link-local, and `.local`
network endpoints require a local-network caveat in the contract.

## WebMCP

On Chromium, the runtime feature-detects `document.modelContext`, which may
require an origin trial or testing flag. It exposes status and telemetry as
read tools; optional command tools use the same confirmation and
acknowledgement path as the dashboard. WebMCP is unavailable on iOS and iPadOS.

## CLI and MCP tools

The `dashboard` CLI and MCP server expose doctor, matrix, validate, generate,
check, gates, smoke, protocol export, and sibling-request operations. Use
`dashboard screenshot <contract>` or MCP `dashboard_screenshot` to capture a
fresh generated app at desktop and mobile viewports; the MCP result attaches
eligible PNGs inline for advisory visual review.

## Architecture and layout

The `.dash.json` contract is the source of truth. Python validates contracts,
generates files, and exposes CLI/MCP tools. The dependency-free TypeScript
runtime handles browser APIs and protocol framing. Routes fail closed unless
declared and detected; hazardous controls require confirmation. Sibling agents
cooperate through copied contracts and JSON artifacts, never code imports.

- `src/dashboard/`: contracts, matrix, gates, generation, and CLI/MCP.
- `runtime/`: TypeScript runtime, Node tests, and Playwright E2E.
- `examples/`: smart-kettle and bench-meter contracts.
- `plugins/dashboard/`: OpenHands agents, commands, skills, hooks, and launcher.
- `docker/`: pinned dashboard-tools environment for full gates.
- `docs/`: operations, decisions, and browser API research.

## Verification

The launcher defaults to Docker and fails closed unless Docker and a tools
image resolve. The local commands below build and select `dashboard-tools:local`;
set `DASHBOARD_LAUNCH_MODE=host` to run on the host, or `auto` to retain the
previous Docker-when-available behavior.

CI workflows use `ubuntu-26.04`; workflow lint runs actionlint and zizmor.
Releases wait for CI and workflow lint on the version-bump branch and verify a
remote plugin install before publishing release archives.

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/ && cd ..
docker build -f docker/dashboard-tools.Dockerfile -t dashboard-tools:local .
export DASHBOARD_TOOLS_IMAGE=dashboard-tools:local
export DASHBOARD_LAUNCH_MODE=docker
export DASHBOARD_SRC="$PWD/src"
export OPENHANDS_PROJECT_DIR="$PWD"
launcher=plugins/dashboard/scripts/dashboard_launcher.py
python3 "$launcher" generate examples/smart-kettle/smart-kettle.dash.json
python3 "$launcher" gates examples/smart-kettle/smart-kettle.dash.json
python3 "$launcher" generate examples/bench-meter/bench-meter.dash.json
python3 "$launcher" gates examples/bench-meter/bench-meter.dash.json
```

The launcher runs gates in an internal Docker network without Internet egress.

## License

BSD-3-Clause. See [LICENSE](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md).

## 日本語

dashboard-agent は、接続デバイス用ブラウザーダッシュボードの開発者向け
VibeBB OpenHands プラグインです。JSON 契約がデバイス接続ルートと操作を
宣言します。契約では `ios` と `ipados` を個別に宣言します。

### プラットフォーム対応表

| OS | ブラウザー | 利用可能なトランスポート | 注意事項 |
| --- | --- | --- | --- |
| Windows | Chrome、Edge、Opera（5 種すべて）；Firefox（ネットワークのみ）；Tauri v2 | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel；Tauri ネイティブ BLE / serial | OS ドライバーが WebUSB インターフェースを使用中の場合があります。 |
| macOS | Chrome、Edge、Opera（5 種すべて）；Safari、Firefox（ネットワークのみ）；Tauri v2 | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel；Tauri ネイティブ BLE / serial | OS ドライバーが WebUSB インターフェースを使用中の場合があります。 |
| Linux | Chrome、Edge、Opera（5 種すべて）；Firefox（ネットワークのみ）；Tauri v2 | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel；Tauri ネイティブ BLE / serial | Web Bluetooth には Chromium フラグと BlueZ が必要です。Tauri の WebRTC は WebKitGTK ビルドに依存します。WebUSB は OS ドライバーが使用中の場合があります。 |
| BSD | BSD Chromium ポート、Firefox（ネットワークのみ） | WebSocket、WebRTC DataChannel | Web Bluetooth は無効、Web Serial は未ビルドです。FreeBSD / NetBSD の WebUSB は fake のみです。OpenBSD では libusb バックエンドがビルドされますが未検証のため提供しません。WebMCP には Chromium のテスト / Origin Trial 機能が必要です。[詳細](docs/research/bsd-chromium.md)。 |
| ChromeOS | Chrome、Edge、Opera（5 種すべて） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | WebUSB は OS ドライバーが使用していないインターフェースを必要とする場合があります。管理対象端末では API が制限されることがあります。管理ポリシーを確認してください。 |
| iOS | Safari、Chrome、Edge、Firefox（WebKit、ネットワークのみ）；Bluefy（ネットワーク、Web Bluetooth）；Tauri v2 | WebSocket、WebRTC DataChannel；Bluefy Web Bluetooth；Tauri ネイティブ BLE | Tauri serial は iOS 非対応です。Bluefy の通知機能は不安定な場合があります。 |
| iPadOS | Safari、Chrome、Edge、Firefox（WebKit、ネットワークのみ）；Bluefy（ネットワーク、Web Bluetooth）；Tauri v2 | WebSocket、WebRTC DataChannel；Bluefy Web Bluetooth；Tauri ネイティブ BLE | WebUSB / Web Serial ルートはありません。Tauri serial も非対応です。Bluefy の通知機能は不安定な場合があります。 |
| Android | Chrome、Edge、Opera（5 種すべて）；Firefox、Samsung Internet（ネットワークのみ）；Tauri v2 | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel；Tauri ネイティブ BLE / serial | WebUSB / Web Serial はドライバーや対応デバイスに制限があります。 |

### ネイティブシェル（Tauri v2）

Tauri ルートでは Windows、macOS、Linux、Android、iOS、iPadOS でネイティブ
BLE を利用できます。ネイティブ serial は Windows、macOS、Linux、Android
のみ対応します。iPadOS は Tauri の iOS ターゲットを使います。デバイス選択
には画面内のピッカーを使い、接続には明示的なクリックが必要です。WebSocket
と WebRTC は WebView のルートです。`dashboard generate` は契約に
`shell.tauri` がある場合だけ `out/<name>/tauri/` を生成します。生成した
アプリは次の手順で起動できます。

```bash
cd examples/smart-kettle/out/smart-kettle/tauri
npm install
npx tauri dev
```

雛形の README にデスクトップ / モバイルのビルド方法と OS ごとの前提条件を記載
しています。WebMCP はデバイス選択や接続ツールを公開しません。

### CLI と MCP ツール

`dashboard` CLI と MCP サーバーでは doctor、matrix、validate、generate、check、
gates、smoke、protocol export、sibling request を利用できます。
`dashboard screenshot <contract>` または MCP `dashboard_screenshot` は、最新の
生成アプリをデスクトップ / モバイルで撮影します。MCP は対象 PNG をインラインで
添付し、表示確認は助言として扱います。

## トランスポートと WebMCP

ランタイムは Web Bluetooth、WebUSB、Web Serial、Tauri ネイティブ BLE / serial、
WebSocket、WebRTC DataChannel を使用します。プライベート IP、リンクローカル、`.local`
エンドポイントには、契約でローカルネットワークの注意事項が必要です。

Chromium では `document.modelContext` を検出して WebMCP を有効にします。
Origin Trial またはテスト用フラグが必要な場合があります。
標準では状態とテレメトリーを読み取り専用ツールとして公開します。任意の操作
ツールもダッシュボードと同じ確認・ACK 手順を通ります。iOS / iPadOS では
WebMCP を利用できません。

## 検証

`dashboard-tools` イメージのゲートは、ランチャーがインターネットへ接続できない
内部 Docker ネットワークで実行します。検証方法は上記の Verification コマンドを
参照してください。

## ライセンス

BSD-3-Clause。詳細は [LICENSE](LICENSE) と
[third-party notices](THIRD_PARTY_NOTICES.md) を参照してください。
