# Design a device dashboard with AI

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/VibeBB/dashboard-agent)

[VibeBB](https://vibebb.org/) dashboard is an OpenHands plugin for turning a
device's firmware interface into a usable, safety-aware web dashboard. It
helps you describe the device, choose where it should work, and review the
generated result with an AI agent.

You stay in control of the product decisions. The dashboard plugin does not
write or flash firmware: it creates the user interface and the protocol
artifacts that help the interface communicate with firmware.

## What you provide

- A plain-language description of the device, its telemetry, and the things a
  person should be able to control.
- The device's firmware contract, if one exists. The dashboard can bind a
  copied contract by SHA-256 and map its messages to dashboard widgets.
- The browsers and operating systems that matter to you, including whether
  you want a web app, an optional Tauri desktop/mobile shell, or both.
- Photos, sketches, screen references, and known constraints. The agent can
  ask questions when behavior or safety details are unclear.

## What you get back

- A generated web app with telemetry displays, device controls, and connection
  status.
- An optional Tauri desktop/mobile shell scaffold when the contract declares
  one.
- A protocol export and generated C protocol header/codec projections for
  firmware handoff.
- Static and full gate reports, plus desktop and mobile screenshots for
  review.
- Append-only decision, stage-impression, and vision-review records. These
  explain design choices and observations; they are advisory, not gate results.

## Start in AgentCanvas or OpenHands

1. Install the VibeBB `dashboard` plugin using your AgentCanvas/OpenHands
   plugin manager.
2. Install and start Docker. The plugin launcher uses Docker and its pinned
   `dashboard-tools` image by default; it does not silently switch to host
   execution. The first full run may need to pull the image.
3. Start a chat and describe the device, or run `/dashboard:design`.

For example:

> Help me design a safe dashboard for this battery-powered garden pump. Use
> the attached firmware contract, photos, and sketch. I need Chrome on Android
> and a Tauri desktop app on Linux. Show pressure and battery telemetry, and
> require confirmation before starting or stopping the pump. Ask me about
> anything the contract or pictures do not make clear.

The agent validates the design, generates the app, runs the available gates,
and asks for review of desktop/mobile screenshots. Full gates use the
Docker-based toolchain.

## Working with VibeBB sister plugins

The dashboard can bind firmware contracts and export protocol artifacts
without importing or editing firmware-project files. The UX-creator plugin
can direct design work through dashboard liaison requests; use
`dashboard_ux_inbox` and `dashboard_ux_respond` to review and answer them.
Circuit, mechanical, FPGA, simulation, production-engineering, documentation,
wire, and Bard plugins can exchange pinned JSON contracts or change requests
through their own workflows. Each project remains owned by its plugin.

## Safety and limits

- Deterministic gates are authoritative. AI observations and VRP records are
  advisory and never turn a failing gate into a pass.
- Hazardous controls require an in-page confirmation. Bluetooth, USB, and
  Serial device selection requires a secure context and an explicit user
  gesture.
- The dashboard does not flash devices or change firmware.
- Browser and operating-system support depends on the declared route; a missing
  route is unsupported, not a promise. See the matrix below.
- The default launcher and full-gate tools require Docker. Explicit
  `DASHBOARD_LAUNCH_MODE=host` is a developer-only option and requires
  `DASHBOARD_SRC`.
- WebMCP is optional and browser-limited. It does not expose device selection
  or connection tools; optional command tools keep the same confirmation and
  acknowledgement path as the dashboard.

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

## Project and license

The project is maintained by VibeBB and is licensed under BSD-3-Clause. See
[the VibeBB website](https://vibebb.org/) and the repository
[license](LICENSE). For technical details, see the
[documentation index](docs/README.md).

## 日本語

# AI でデバイス用ダッシュボードを設計する

[VibeBB](https://vibebb.org/) の dashboard は、デバイスのファームウェア
インターフェースを、使いやすく安全性に配慮した Web ダッシュボードにする
OpenHands プラグインです。デバイスの説明、対応させたい環境、生成結果の確認を
AI エージェントと進められます。

製品の判断は利用者が行います。dashboard プラグインはファームウェアを書いたり
書き込んだりしません。ユーザーインターフェースと、ファームウェアとの通信に
使うプロトコル成果物を生成します。

## 用意するもの

- デバイス、そのテレメトリー、人が操作したい機能についての平易な説明。
- 利用可能であればデバイスのファームウェア契約。コピーした契約を SHA-256 で
  固定し、そのメッセージをダッシュボードのウィジェットに対応付けられます。
- 対応させたいブラウザーと OS。Web アプリ、任意の Tauri デスクトップ / モバイル
  シェル、または両方が必要かも伝えてください。
- 写真、スケッチ、画面の参考資料、既知の制約。動作や安全性が不明な場合、
  エージェントが質問します。

## 受け取れるもの

- テレメトリー表示、デバイス操作、接続状態を含む生成 Web アプリ。
- 契約で宣言した場合の、任意の Tauri デスクトップ / モバイルシェルの雛形。
- ファームウェア連携用のプロトコルエクスポートと、生成された C プロトコル
  ヘッダー / codec の投影成果物。
- 静的ゲートとフルゲートのレポート、およびレビュー用のデスクトップ / モバイル
  スクリーンショット。
- 設計判断や観察を説明する追記専用の decision、stage-impression、
  vision-review レコード。これらは助言であり、ゲート結果ではありません。

## AgentCanvas または OpenHands で始める

1. AgentCanvas / OpenHands のプラグイン管理機能で VibeBB の `dashboard`
   プラグインをインストールします。
2. Docker をインストールして起動します。プラグインランチャーは既定で Docker と
   固定された `dashboard-tools` イメージを使い、暗黙にホスト実行へ切り替えません。
   初回のフル実行ではイメージの取得が必要になる場合があります。
3. チャットを開始してデバイスを説明するか、`/dashboard:design` を実行します。

プロンプト例:

> このバッテリー駆動の庭用ポンプに、安全なダッシュボードを設計してください。
> 添付したファームウェア契約、写真、スケッチを使ってください。Android の Chrome
> と Linux の Tauri デスクトップアプリが必要です。圧力とバッテリー残量を表示し、
> ポンプの開始 / 停止には確認を必須にしてください。契約や画像で分からない点は
> 質問してください。

エージェントは設計を検証し、アプリを生成し、利用可能なゲートを実行し、
デスクトップ / モバイルのスクリーンショットのレビューを依頼します。フルゲートは
Docker ベースのツール環境を使います。

## VibeBB の姉妹プラグインとの連携

dashboard はファームウェア契約を固定してプロトコル成果物を出力できますが、
ファームウェアプロジェクトのファイルを import したり編集したりしません。
UX-creator プラグインは dashboard の liaison リクエストを通じて設計作業を依頼
できます。`dashboard_ux_inbox` と `dashboard_ux_respond` で確認して回答します。
Circuit、mechanical、FPGA、simulation、production-engineering、documentation、
wire、Bard の各プラグインとは、それぞれのワークフローで SHA-256 固定 JSON 契約や
変更リクエストを交換できます。各プロジェクトの所有権は対応するプラグインに
あります。

## 安全性と制限

- 決定的なゲートが正式な判定です。AI の観察と VRP レコードは助言であり、失敗した
  ゲートを pass に変えるものではありません。
- 危険を伴う操作には画面内確認が必要です。Bluetooth、USB、Serial のデバイス選択
  にはセキュアなコンテキストと明示的なユーザー操作が必要です。
- dashboard はデバイスへファームウェアを書き込みません。
- ブラウザーと OS の対応状況は宣言されたルートによって異なります。ルートがない
  場合は非対応であり、対応の約束ではありません。下記の表を確認してください。
- 既定のランチャーとフルゲートには Docker が必要です。明示的な
  `DASHBOARD_LAUNCH_MODE=host` は開発者専用で、`DASHBOARD_SRC` が必要です。
- WebMCP は任意で、利用できるブラウザーも限られます。デバイスの選択や接続の
  ツールは公開しません。任意の操作ツールにもダッシュボードと同じ確認および
  acknowledgement 手順が適用されます。

## プラットフォーム対応

表はブラウザーと OS ごとに利用可能なルートを示します。契約では `ios` と
`ipados` を個別に宣言します。両方の例を参照してください。

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

## プロジェクトとライセンス

本プロジェクトは VibeBB が管理し、BSD-3-Clause ライセンスで公開しています。
[VibeBB のウェブサイト](https://vibebb.org/)とリポジトリーの
[ライセンス](LICENSE)、技術情報の
[ドキュメント一覧](docs/README.md)を参照してください。
