export type WireType = "u8" | "i8" | "u16" | "i16" | "u32" | "i32" | "f32" | "bool";
export type MessageDirection = "device_to_host" | "host_to_device";
export type TransportKind =
  | "web_bluetooth"
  | "webusb"
  | "web_serial"
  | "websocket"
  | "webrtc"
  | "tauri_ble"
  | "tauri_serial";

export interface FieldConfig {
  name: string;
  type: WireType;
  unit?: string | null;
  scale: number;
  min?: number | null;
  max?: number | null;
}

export interface MessageConfig {
  id: number;
  name: string;
  direction: MessageDirection;
  ack: boolean;
  fields: FieldConfig[];
}

interface TransportConfigBase {
  id: string;
}

export type TransportConfig =
  | (TransportConfigBase & {
    kind: "web_bluetooth";
    service_uuid: string;
    rx_characteristic: string;
    tx_characteristic: string;
    name_prefix?: string | null;
  })
  | (TransportConfigBase & {
    kind: "tauri_ble";
    service_uuid: string;
    rx_characteristic: string;
    tx_characteristic: string;
    name_prefix?: string | null;
  })
  | (TransportConfigBase & {
    kind: "webusb";
    vendor_id: number;
    product_id?: number | null;
    interface_class: number;
    interface_number: number;
    endpoint_in: number;
    endpoint_out: number;
  })
  | (TransportConfigBase & {
    kind: "web_serial";
    baud_rate: number;
    usb_vendor_id?: number | null;
    usb_product_id?: number | null;
    bluetooth_service_class_id?: string | null;
  })
  | (TransportConfigBase & {
    kind: "tauri_serial";
    baud_rate: number;
    usb_vendor_id?: number | null;
    usb_product_id?: number | null;
  })
  | (TransportConfigBase & {
    kind: "websocket";
    url: string;
    subprotocol?: string | null;
  })
  | (TransportConfigBase & {
    kind: "webrtc";
    signaling_url: string;
    data_channel: string;
    ordered: boolean;
    ice_servers: Array<{ urls: string[] }>;
  });

export interface PlatformConfig {
  os: string;
  status: "supported" | "unsupported";
  reason?: string | null;
  routes: Array<{
    browser: string;
    transport: string;
    acknowledged_caveats: string[];
  }>;
}

export interface WidgetConfig {
  id: string;
  kind: "value" | "gauge" | "chart" | "indicator" | "button" | "toggle" | "slider";
  label: string;
  source?: string | null;
  command?: string | null;
  field?: string | null;
  hazard: boolean;
  confirm: boolean;
}

export interface DashboardContract {
  name: string;
  description: string;
  protocol: {
    max_frame_bytes: number;
    messages: MessageConfig[];
  };
  transports: TransportConfig[];
  platforms: PlatformConfig[];
  widgets: WidgetConfig[];
  session: {
    connect_timeout_ms: number;
    ack_timeout_ms: number;
    reconnect: { max_attempts: number; backoff_ms: number };
  };
  webmcp?: {
    enabled: boolean;
    expose_controls: boolean;
    origin_trial_token?: string | null;
  } | null;
}

export interface DashboardConfig {
  contract_sha256: string;
  contract: DashboardContract;
  routes: Array<{
    os: string;
    browser: string;
    transport: string;
    kind: TransportKind;
    support: string;
    caveats: string[];
    caveat_text: Record<string, string>;
  }>;
  webmcp_tools: WebMcpToolDefinition[];
}

export interface WebMcpToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations: {
    readOnlyHint?: boolean;
    untrustedContentHint?: boolean;
    consequentialHint?: boolean;
  };
}

export type TelemetryValues = Record<string, Record<string, number | boolean>>;
