"""Stable JSON and Markdown serialization for dashboard gate reports."""

from __future__ import annotations

from pathlib import Path

from .gates import GateReport, report_markdown


def write_outputs(report: GateReport, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report.design}.dash-report.json"
    markdown_path = out_dir / f"{report.design}.dash-report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    return [json_path, markdown_path]
