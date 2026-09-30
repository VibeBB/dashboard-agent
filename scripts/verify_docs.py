"""Verify relative Markdown links and the ADR index."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_PARTS = {".git", ".venv", "node_modules", "out"}


def check_links() -> list[str]:
    errors: list[str] = []
    for markdown in ROOT.rglob("*.md"):
        if any(part in SKIP_PARTS for part in markdown.parts):
            continue
        for target in LINK_PATTERN.findall(markdown.read_text(encoding="utf-8")):
            target = target.strip().strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path = (markdown.parent / unquote(target.split("#", 1)[0])).resolve()
            if not path.exists():
                errors.append(f"{markdown.relative_to(ROOT)}: missing {target}")
    return errors


def check_adr_index() -> list[str]:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    return [
        f"docs/README.md: missing ADR {adr.relative_to(ROOT / 'docs').as_posix()}"
        for adr in sorted((ROOT / "docs/adr").glob("ADR-*.md"))
        if adr.relative_to(ROOT / "docs").as_posix() not in index
    ]


def check_platform_readme() -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    english_rows = (
        "| OS | Browsers | Usable transports | Caveats |",
        "| Windows |",
        "| macOS |",
        "| Linux |",
        "| BSD |",
        "| ChromeOS |",
        "| iOS |",
        "| iPadOS |",
        "| Android |",
    )
    japanese_rows = (
        "| OS | ブラウザー | 利用可能なトランスポート | 注意事項 |",
        "| Windows |",
        "| macOS |",
        "| Linux |",
        "| BSD |",
        "| ChromeOS |",
        "| iOS |",
        "| iPadOS |",
        "| Android |",
    )
    errors: list[str] = []
    if "## 日本語" not in readme:
        return ["README.md: missing Japanese section."]
    english, japanese = readme.split("## 日本語", maxsplit=1)
    for section, table in ((english, english_rows), (japanese, japanese_rows)):
        positions = [section.find(row) for row in table]
        if any(position < 0 for position in positions):
            errors.append("README.md: missing a required platform table row.")
        elif positions != sorted(positions):
            errors.append("README.md: platform table rows are out of order.")
    if "education" in readme.casefold() or "教育機関" in readme:
        errors.append("README.md: unexpected education framing in platform support.")
    return errors


def main() -> int:
    errors = check_links() + check_adr_index() + check_platform_readme()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("documentation verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
