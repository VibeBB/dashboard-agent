from __future__ import annotations

from pathlib import Path
from typing import cast

from pytest import MonkeyPatch

from dashboard import screenshots, service, servo
from dashboard.contract import load_contract
from dashboard.gates import Check, GateReport
from dashboard.interchange import sha256_file
from dashboard.service import matrix_payload, screenshot_payload, validate_payload
from dashboard.servo import SmokeResult

ROOT = Path(__file__).resolve().parents[1]


def test_matrix_payload_includes_bsd_network_only_routes() -> None:
    payload = matrix_payload()
    rows = payload["rows"]
    assert isinstance(rows, list)
    bsd_rows = [
        cast(dict[str, object], row)
        for row in cast(list[object], rows)
        if isinstance(row, dict) and cast(dict[str, object], row).get("os") == "bsd"
    ]

    assert {(row["browser"], row["transport"]) for row in bsd_rows} == {
        ("chrome", "websocket"),
        ("chrome", "webrtc"),
        ("firefox", "websocket"),
        ("firefox", "webrtc"),
    }
    caveats = payload["caveats"]
    assert isinstance(caveats, dict)
    assert "bsd-hardware-apis-unverified" in cast(dict[str, object], caveats)


def test_validation_payload_accepts_ipados_contract_declarations() -> None:
    payload = validate_payload(ROOT / "examples/smart-kettle/smart-kettle.dash.json")

    assert payload["verdict"] == "pass"
    platforms = payload["platforms"]
    assert isinstance(platforms, list)
    platform_names = cast(list[object], platforms)
    assert platform_names.count("ios") == 1
    assert platform_names.count("ipados") == 1


def test_screenshot_payload_requires_fresh_generation(tmp_path: Path) -> None:
    contract = ROOT / "examples/smart-kettle/smart-kettle.dash.json"

    payload = screenshot_payload(contract, tmp_path / "out")

    assert payload["verdict"] == "fail"
    assert payload["stage"] == "screenshot"
    assert "cannot load generation manifest" in cast(str, payload["detail"])
    assert payload["images"] == []
    assert payload["vision_review"] == []


def test_image_payloads_bind_images_to_vision_reviews(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    contract_path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    contract = load_contract(contract_path)
    desktop = tmp_path / "desktop.png"
    mobile = tmp_path / "mobile.png"
    servo_image = tmp_path / "servo.png"
    other = tmp_path / "intake.png"
    images = (desktop, mobile, servo_image, other)
    for index, image in enumerate(images):
        image.write_bytes(f"image-{index}".encode())

    monkeypatch.setattr(service, "load_contract", lambda _path: contract)
    monkeypatch.setattr(service, "generated_freshness", lambda _contract, _generated: [])
    monkeypatch.setattr(
        service,
        "capture",
        lambda _generated, _out: screenshots.CaptureResult(
            ok=True,
            detail="captured",
            images=[
                screenshots.ScreenImage(
                    name=image.stem,
                    path=image,
                    width=1280,
                    height=800,
                    sha256="a" * 64,
                    bytes=image.stat().st_size,
                )
                for image in images[:2]
            ],
        ),
    )
    monkeypatch.setattr(
        service,
        "run_gates",
        lambda _contract_path, _out, *, full: GateReport(
            design=contract.name,
            scope="full" if full else "static",
            contract_sha256="a" * 64,
            verdict="pass",
            checks=[
                Check(id="visual.capture", status="pass", evidence=[str(desktop), str(mobile)]),
                Check(
                    id="smoke.servo",
                    status="pass",
                    evidence=[str(servo_image), str(other)],
                ),
            ],
        ),
    )
    monkeypatch.setattr(service, "write_outputs", lambda _report, _out: [])
    monkeypatch.setattr(
        servo,
        "smoke",
        lambda _generated: SmokeResult(
            ok=True,
            detail="Servo rendered",
            screenshot=servo_image,
        ),
    )

    screenshot = screenshot_payload(contract_path, tmp_path / "out")
    gates_payload = service.gates_payload(contract_path, tmp_path / "out", full=True)
    smoke_payload = service.smoke_payload(contract_path, tmp_path / "out")

    for payload, expected_paths in (
        (screenshot, [str(desktop), str(mobile)]),
        (gates_payload, [str(desktop), str(mobile), str(servo_image), str(other)]),
        (smoke_payload, [str(servo_image)]),
    ):
        assert payload["images"] == expected_paths
        reviews = cast(list[dict[str, str]], payload["vision_review"])
        assert [review["image_path"] for review in reviews] == expected_paths
        assert all(review["record_with"] == "dashboard_record_vision_review" for review in reviews)
        for review in reviews:
            assert set(review) == {"image_path", "sha256", "checklist", "record_with"}
            assert review["sha256"] == sha256_file(Path(review["image_path"]))

    screenshot_reviews = cast(list[dict[str, str]], screenshot["vision_review"])
    gate_reviews = cast(list[dict[str, str]], gates_payload["vision_review"])
    smoke_reviews = cast(list[dict[str, str]], smoke_payload["vision_review"])

    assert [item["checklist"] for item in screenshot_reviews] == [
        "dashboard-desktop",
        "dashboard-mobile",
    ]
    assert [item["checklist"] for item in gate_reviews] == [
        "dashboard-desktop",
        "dashboard-mobile",
        "servo-render",
        "dashboard-image",
    ]
    assert smoke_reviews[0]["checklist"] == "servo-render"
