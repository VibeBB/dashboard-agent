# Browser hardware API support research

Support declarations are explicit per contract. The matrix is maintained in
`src/dashboard/matrix.py`; this summary records the platform caveats behind it.

| API / route | Verified support | Caveat |
| --- | --- | --- |
| Web Bluetooth | Chromium on Windows, macOS, ChromeOS, and Android | Linux requires browser flag and BlueZ; managed ChromeOS device APIs may be restricted by admin policy; iOS/iPadOS WebKit does not implement it |
| Bluefy Web Bluetooth | Third-party iOS/iPadOS WebKit browser | Notifications can be unreliable; show `bluefy-notifications` |
| WebUSB | Chromium desktop, ChromeOS, and Android | The requested interface may be claimed by an OS driver; Android driver limitations apply; managed Chromebooks may restrict device APIs, so check your admin policy |
| Web Serial | Chromium desktop and Android | Android USB serial and RFCOMM support is limited |
| WebSocket | Broad browser support | HTTPS requires `wss://`; private/link-local endpoints and `*.local` require local-network access |
| WebRTC DataChannel | Broad browser support, including iOS/iPadOS Safari | Requires signaling and ICE configuration |
| WebMCP | Chromium 149+ origin trial / testing flag | Feature-detect `document.modelContext`; other browsers simply omit tools |
| BSD Chromium ports | Chromium ports and Firefox | Web Bluetooth is disabled, Web Serial is not built, and WebUSB is fake-only or unverified; offer only WebSocket and WebRTC. WebMCP is feature-flag/origin-trial only. See [BSD port research](bsd-chromium.md) |

Primary references:

- [Web Bluetooth API](https://developer.mozilla.org/docs/Web/API/Web_Bluetooth_API)
- [WebUSB API](https://developer.mozilla.org/docs/Web/API/USB)
- [Web Serial API](https://developer.mozilla.org/docs/Web/API/Web_Serial_API)
- [WebSocket API](https://developer.mozilla.org/docs/Web/API/WebSocket)
- [WebRTC API](https://developer.mozilla.org/docs/Web/API/WebRTC_API)
- [Chrome WebMCP imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api)
- [Chrome WebMCP declarative API](https://developer.chrome.com/docs/ai/webmcp/declarative-api)
- [WebMCP explainer](https://github.com/webmachinelearning/webmcp)
