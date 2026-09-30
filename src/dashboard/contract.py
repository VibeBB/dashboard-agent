"""The dashboard contract is the source of truth for generated applications."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SLUG = r"^[a-z0-9][a-z0-9-]{0,62}$"
SNAKE = r"^[a-z][a-z0-9_]*$"
UUID_PATTERN = r"^(?:0x[0-9a-f]{4}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
SHA256 = r"^[0-9a-f]{64}$"
SEMVER = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
REVERSE_DNS = (
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)

U8_MAX = 255
WIRE_TYPES: dict[str, tuple[int, float, float]] = {
    "u8": (1, 0, 255),
    "i8": (1, -128, 127),
    "u16": (2, 0, 65535),
    "i16": (2, -32768, 32767),
    "u32": (4, 0, 4294967295),
    "i32": (4, -2147483648, 2147483647),
    "f32": (4, -3.4028235e38, 3.4028235e38),
    "bool": (1, 0, 1),
}
BAUD_RATES = frozenset(
    {
        9600,
        14400,
        19200,
        28800,
        38400,
        57600,
        115200,
        230400,
        460800,
        921600,
        1000000,
        1500000,
        2000000,
        3000000,
    }
)

Name = Annotated[str, StringConstraints(pattern=SLUG)]
SnakeName = Annotated[str, StringConstraints(pattern=SNAKE)]
OSName = Literal["windows", "macos", "linux", "bsd", "chromeos", "android", "ios", "ipados"]
BrowserName = Literal[
    "chrome", "edge", "opera", "samsung_internet", "firefox", "safari", "bluefy", "tauri"
]
TransportKind = Literal[
    "web_bluetooth",
    "webusb",
    "web_serial",
    "websocket",
    "webrtc",
    "tauri_ble",
    "tauri_serial",
]
TauriTarget = Literal["windows", "macos", "linux", "android", "ios"]


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FieldSpec(StrictModel):
    name: SnakeName
    type: Literal["u8", "i8", "u16", "i16", "u32", "i32", "f32", "bool"]
    unit: str | None = None
    scale: float = Field(default=1.0, strict=True, gt=0)
    min: float | None = Field(default=None, strict=True)
    max: float | None = Field(default=None, strict=True)


class Message(StrictModel):
    id: int = Field(strict=True, ge=0, le=254)
    name: SnakeName
    direction: Literal["device_to_host", "host_to_device"]
    ack: bool = False
    fields: list[FieldSpec] = Field(default_factory=list[FieldSpec])

    @model_validator(mode="after")
    def validate_ack_direction(self) -> Message:
        if self.ack and self.direction != "host_to_device":
            raise ValueError("ack is only valid for host_to_device messages")
        return self


class Protocol(StrictModel):
    framing: Literal["cobs-crc16"]
    max_frame_bytes: int = Field(strict=True, ge=16, le=512)
    messages: list[Message] = Field(min_length=1)


class TransportBase(StrictModel):
    id: Name


class BleTransportBase(TransportBase):
    service_uuid: str
    rx_characteristic: str
    tx_characteristic: str
    name_prefix: str | None = None

    @field_validator("service_uuid", "rx_characteristic", "tx_characteristic")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        if not re.fullmatch(UUID_PATTERN, value):
            raise ValueError("UUID must be lowercase canonical 128-bit or 0x-prefixed 16-bit")
        return value


class WebBluetoothTransport(BleTransportBase):
    kind: Literal["web_bluetooth"]


class TauriBleTransport(BleTransportBase):
    kind: Literal["tauri_ble"]


class WebUsbTransport(TransportBase):
    kind: Literal["webusb"]
    vendor_id: int = Field(strict=True, ge=0, le=0xFFFF)
    product_id: int | None = Field(default=None, strict=True, ge=0, le=0xFFFF)
    interface_class: int = Field(strict=True, ge=0, le=0xFF)
    interface_number: int = Field(strict=True, ge=0, le=0xFF)
    endpoint_in: int = Field(strict=True, ge=1, le=0xFF)
    endpoint_out: int = Field(strict=True, ge=1, le=0xFF)


class SerialTransportBase(TransportBase):
    baud_rate: int = Field(strict=True, ge=9600, le=3000000)
    usb_vendor_id: int | None = Field(default=None, strict=True, ge=0, le=0xFFFF)
    usb_product_id: int | None = Field(default=None, strict=True, ge=0, le=0xFFFF)
    bluetooth_service_class_id: str | None = None

    @field_validator("baud_rate")
    @classmethod
    def validate_baud_rate(cls, value: int) -> int:
        if value not in BAUD_RATES:
            raise ValueError("baud_rate must be a standard supported rate")
        return value


class WebSerialTransport(SerialTransportBase):
    kind: Literal["web_serial"]


class TauriSerialTransport(SerialTransportBase):
    kind: Literal["tauri_serial"]


class WebSocketTransport(TransportBase):
    kind: Literal["websocket"]
    url: str = Field(min_length=1)
    subprotocol: str | None = None


class IceServer(StrictModel):
    urls: list[str] = Field(min_length=1)


class WebRtcTransport(TransportBase):
    kind: Literal["webrtc"]
    signaling_url: str = Field(min_length=1)
    data_channel: str = "dash"
    ordered: bool = True
    ice_servers: list[IceServer] = Field(default_factory=list[IceServer])


Transport = Annotated[
    WebBluetoothTransport
    | TauriBleTransport
    | WebUsbTransport
    | WebSerialTransport
    | TauriSerialTransport
    | WebSocketTransport
    | WebRtcTransport,
    Field(discriminator="kind"),
]


class Route(StrictModel):
    browser: BrowserName
    transport: Name
    acknowledged_caveats: list[str] = Field(default_factory=list)


class PlatformDecl(StrictModel):
    os: OSName
    status: Literal["supported", "unsupported"]
    routes: list[Route] = Field(default_factory=list[Route])
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> PlatformDecl:
        if self.status == "supported" and (not self.routes or self.reason is not None):
            raise ValueError("supported platforms require routes and cannot have a reason")
        if self.status == "unsupported" and (self.routes or not self.reason):
            raise ValueError("unsupported platforms require a reason and cannot have routes")
        return self


class Widget(StrictModel):
    id: Name
    kind: Literal["value", "gauge", "chart", "indicator", "button", "toggle", "slider"]
    label: str = Field(min_length=1)
    source: str | None = None
    command: SnakeName | None = None
    field: SnakeName | None = None
    hazard: bool = False
    confirm: bool = False


class Reconnect(StrictModel):
    max_attempts: int = Field(default=5, strict=True, ge=0, le=20)
    backoff_ms: int = Field(default=1000, strict=True, ge=100, le=60000)


class SessionConfig(StrictModel):
    connect_timeout_ms: int = Field(default=10000, strict=True, ge=1000, le=60000)
    ack_timeout_ms: int = Field(default=1000, strict=True, ge=50, le=10000)
    reconnect: Reconnect = Field(default_factory=Reconnect)


class WasmModule(StrictModel):
    id: Name
    sources: list[str] = Field(min_length=1)
    exports: list[str] = Field(min_length=1)


class WasmConfig(StrictModel):
    modules: list[WasmModule] = Field(default_factory=list[WasmModule])


class ImportRef(StrictModel):
    from_system: Literal["firmware", "circuit", "ux-creator", "mech", "wire", "bard"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256)


class WebMcpConfig(StrictModel):
    enabled: bool = True
    expose_controls: bool = False
    origin_trial_token: str | None = None


class TauriShellConfig(StrictModel):
    identifier: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    version: str = Field(pattern=SEMVER)
    targets: list[TauriTarget] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_targets_unique(self) -> TauriShellConfig:
        if len(self.targets) != len(set(self.targets)):
            raise ValueError("Tauri targets must be unique")
        return self


class ShellConfig(StrictModel):
    tauri: TauriShellConfig | None = None


class Device(StrictModel):
    firmware_contract: str | None = None
    firmware_sha256: str | None = Field(default=None, pattern=SHA256)

    @model_validator(mode="after")
    def validate_firmware_pair(self) -> Device:
        if (self.firmware_contract is None) != (self.firmware_sha256 is None):
            raise ValueError("firmware_contract and firmware_sha256 must be set together")
        return self


class DashboardContract(StrictModel):
    schema_version: Literal[1]
    system: Literal["dashboard"]
    artifact_kind: Literal["dashboard_contract"]
    name: Name
    description: str = Field(min_length=1)
    device: Device
    protocol: Protocol
    transports: list[Transport] = Field(min_length=1)
    platforms: list[PlatformDecl] = Field(min_length=1)
    widgets: list[Widget] = Field(min_length=1)
    session: SessionConfig = Field(default_factory=SessionConfig)
    shell: ShellConfig | None = None
    wasm: WasmConfig | None = None
    webmcp: WebMcpConfig | None = None
    imports: list[ImportRef] = Field(default_factory=list[ImportRef])


def load_contract(path: str | Path) -> DashboardContract:
    return DashboardContract.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def resolve(contract_path: str | Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    return (Path(contract_path).resolve().parent / candidate).resolve()
