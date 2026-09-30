# dashboard-agent

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
| Windows | Chrome, Edge, Opera (all five); Firefox (network only) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | A WebUSB interface may be claimed by an OS driver. |
| macOS | Chrome, Edge, Opera (all five); Safari and Firefox (network only) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | A WebUSB interface may be claimed by an OS driver. |
| Linux | Chrome, Edge, Opera (all five); Firefox (network only) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | Web Bluetooth needs a Chromium flag and BlueZ; a WebUSB interface may be claimed by an OS driver. |
| BSD | BSD Chromium ports and Firefox (network only) | WebSocket, WebRTC DataChannel | Web Bluetooth is disabled; Web Serial is not built; FreeBSD/NetBSD WebUSB is fake-only. OpenBSD compiles a libusb backend, but it is unverified and not offered. WebMCP needs Chromium's testing/origin-trial feature. [Details](docs/research/bsd-chromium.md). |
| ChromeOS | Chrome, Edge, Opera (all five) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | WebUSB may need an interface not claimed by an OS driver. Managed Chromebooks may restrict device APIs; check your admin policy. |
| iOS | Safari, Chrome, Edge, Firefox (WebKit; network only); Bluefy (network and Web Bluetooth) | WebSocket, WebRTC DataChannel; Bluefy Web Bluetooth | Bluefy notifications can be unreliable. |
| iPadOS | Safari, Chrome, Edge, Firefox (WebKit; network only); Bluefy (network and Web Bluetooth) | WebSocket, WebRTC DataChannel; Bluefy Web Bluetooth | No WebUSB or Web Serial routes. Bluefy notifications can be unreliable. |
| Android | Chrome, Edge, Opera (all five); Firefox and Samsung Internet (network only) | Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC DataChannel | Android WebUSB and Web Serial have device-driver and support limitations. |

## Transports

The runtime supports Web Bluetooth, WebUSB, Web Serial, WebSocket, and WebRTC
DataChannel. Private, link-local, and `.local` network endpoints require a
local-network caveat in the contract.

## WebMCP

On Chromium, the runtime feature-detects `document.modelContext`, which may
require an origin trial or testing flag. It exposes status and telemetry as
read tools; optional command tools use the same confirmation and
acknowledgement path as the dashboard. WebMCP is unavailable on iOS and iPadOS.

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

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/ && cd ..
docker build -f docker/dashboard-tools.Dockerfile -t dashboard-tools:local .
docker run --rm --network none dashboard-tools:local python -m dashboard gates examples/smart-kettle/smart-kettle.dash.json --full
docker run --rm --network none dashboard-tools:local python -m dashboard gates examples/bench-meter/bench-meter.dash.json --full
```

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
| Windows | Chrome、Edge、Opera（5 種すべて）；Firefox（ネットワークのみ） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | OS ドライバーが WebUSB インターフェースを使用中の場合があります。 |
| macOS | Chrome、Edge、Opera（5 種すべて）；Safari、Firefox（ネットワークのみ） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | OS ドライバーが WebUSB インターフェースを使用中の場合があります。 |
| Linux | Chrome、Edge、Opera（5 種すべて）；Firefox（ネットワークのみ） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | Web Bluetooth には Chromium フラグと BlueZ が必要です。WebUSB は OS ドライバーが使用中の場合があります。 |
| BSD | BSD Chromium ポート、Firefox（ネットワークのみ） | WebSocket、WebRTC DataChannel | Web Bluetooth は無効、Web Serial は未ビルドです。FreeBSD / NetBSD の WebUSB は fake のみです。OpenBSD では libusb バックエンドがビルドされますが未検証のため提供しません。WebMCP には Chromium のテスト / Origin Trial 機能が必要です。[詳細](docs/research/bsd-chromium.md)。 |
| ChromeOS | Chrome、Edge、Opera（5 種すべて） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | WebUSB は OS ドライバーが使用していないインターフェースを必要とする場合があります。管理対象端末では API が制限されることがあります。管理ポリシーを確認してください。 |
| iOS | Safari、Chrome、Edge、Firefox（WebKit、ネットワークのみ）；Bluefy（ネットワーク、Web Bluetooth） | WebSocket、WebRTC DataChannel；Bluefy Web Bluetooth | Bluefy の通知機能は不安定な場合があります。 |
| iPadOS | Safari、Chrome、Edge、Firefox（WebKit、ネットワークのみ）；Bluefy（ネットワーク、Web Bluetooth） | WebSocket、WebRTC DataChannel；Bluefy Web Bluetooth | WebUSB / Web Serial ルートはありません。Bluefy の通知機能は不安定な場合があります。 |
| Android | Chrome、Edge、Opera（5 種すべて）；Firefox、Samsung Internet（ネットワークのみ） | Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC DataChannel | WebUSB / Web Serial はドライバーや対応デバイスに制限があります。 |

## トランスポートと WebMCP

ランタイムは Web Bluetooth、WebUSB、Web Serial、WebSocket、WebRTC
DataChannel を使用します。プライベート IP、リンクローカル、`.local`
エンドポイントには、契約でローカルネットワークの注意事項が必要です。

Chromium では `document.modelContext` を検出して WebMCP を有効にします。
Origin Trial またはテスト用フラグが必要な場合があります。
標準では状態とテレメトリーを読み取り専用ツールとして公開します。任意の操作
ツールもダッシュボードと同じ確認・ACK 手順を通ります。iOS / iPadOS では
WebMCP を利用できません。

## 検証

検証方法は上記の Verification コマンドを参照してください。

## ライセンス

BSD-3-Clause。詳細は [LICENSE](LICENSE) と
[third-party notices](THIRD_PARTY_NOTICES.md) を参照してください。
