"""mruby/c Emscripten leg: bytecode compile, WASM build argv, node run."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from dashboard import mrubyc


def _stub(tmp_path: Path, name: str, body: str) -> str:
    stub = tmp_path / name
    stub.write_text(body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(stub)


@pytest.fixture()
def mrubyc_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tree = tmp_path / "mrubyc"
    (tree / "src").mkdir(parents=True)
    (tree / "src/alloc.c").write_text("int a;\n", encoding="utf-8")
    (tree / "src/hal.c").write_text("int skip;\n", encoding="utf-8")
    hal = tree / "hal/emscripten"
    hal.mkdir(parents=True)
    (hal / "hal.c").write_text("int h;\n", encoding="utf-8")
    monkeypatch.setenv(mrubyc.MRUBYC_DIR_ENV, str(tree))
    return tree


def _stub_mrbc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(
        tmp_path,
        "mrbc",
        "#!/bin/sh\n"
        'out=""\nsym=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in -B) sym="$2"; shift 2;; -o) out="$2"; shift 2;; *) shift;; esac\n'
        "done\n"
        'echo "const unsigned char ${sym}[] = {0};" > "$out"\n',
    )
    _stub(
        tmp_path,
        "emcc",
        '#!/bin/sh\nfor last; do :; done\nmkdir -p "$(dirname "$last")" && touch "$last"\n',
    )
    _stub(tmp_path, "node", "#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")


class TestBuildMrubycModule:
    def test_missing_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))
        result = mrubyc.build_mrubyc_module(tmp_path, tmp_path / "out", [], 64 * 1024)
        assert not result.ok
        assert "required tool not found" in result.detail

    def test_missing_mrubyc_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_mrbc(tmp_path, monkeypatch)
        monkeypatch.setenv(mrubyc.MRUBYC_DIR_ENV, str(tmp_path / "absent"))
        result = mrubyc.build_mrubyc_module(tmp_path, tmp_path / "out", [], 64 * 1024)
        assert not result.ok
        assert "mruby/c tree not found" in result.detail

    def test_missing_source(
        self, tmp_path: Path, mrubyc_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_mrbc(tmp_path, monkeypatch)
        result = mrubyc.build_mrubyc_module(
            tmp_path, tmp_path / "out", [tmp_path / "no.rb"], 64 * 1024
        )
        assert not result.ok
        assert "ruby source missing" in result.detail

    def test_build_invokes_mrbc_and_emcc(
        self, tmp_path: Path, mrubyc_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_mrbc(tmp_path, monkeypatch)
        source = tmp_path / "app.rb"
        source.write_text("puts 1\n", encoding="utf-8")
        output = tmp_path / "out"
        result = mrubyc.build_mrubyc_module(tmp_path, output, [source], 32 * 1024)
        assert result.ok, result.detail
        assert (output / "app.c").is_file()
        shim = (output / "mruby_ux_main.c").read_text(encoding="utf-8")
        assert "extern const uint8_t app[];" in shim
        assert "memory_pool[32768]" in shim
        assert "mrbc_create_task(app, 0)" in shim

    def test_mrbc_failure_propagates(
        self, tmp_path: Path, mrubyc_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(tmp_path, "mrbc", "#!/bin/sh\necho bad 1>&2; exit 1\n")
        _stub(tmp_path, "emcc", "#!/bin/sh\nexit 0\n")
        _stub(tmp_path, "node", "#!/bin/sh\nexit 0\n")
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
        source = tmp_path / "app.rb"
        source.write_text("x = \n", encoding="utf-8")
        result = mrubyc.build_mrubyc_module(tmp_path, tmp_path / "out", [source], 64 * 1024)
        assert not result.ok
        assert "app.rb" in result.detail


class TestRunMrubycModule:
    def test_node_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub(tmp_path, "node", "#!/bin/sh\necho vm fail 1>&2; exit 1\n")
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
        result = mrubyc.run_mrubyc_module(tmp_path, tmp_path / "module.mjs")
        assert not result.ok
        assert "vm fail" in result.detail
