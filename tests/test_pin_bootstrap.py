from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".scripts" / "pin_bootstrap.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pin_bootstrap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PIN = load_script()


def test_the_pinned_scripts_default_to_the_tag_and_keep_the_override(tmp_path: Path) -> None:
    PIN.pin(ROOT, tmp_path, "v1.2.3")

    ps1 = (tmp_path / "install.ps1").read_text(encoding="utf-8")
    sh = (tmp_path / "install.sh").read_text(encoding="utf-8")
    assert "{ 'v1.2.3' }" in ps1
    assert "'main'" not in ps1
    assert "$env:TERMINAL_SETUP_REF" in ps1
    assert "${TERMINAL_SETUP_REF:-v1.2.3}" in sh
    assert ":-main" not in sh


def test_pinning_changes_only_the_default_ref(tmp_path: Path) -> None:
    PIN.pin(ROOT, tmp_path, "v1.2.3")

    for name in ("install.ps1", "install.sh"):
        source = (ROOT / name).read_text(encoding="utf-8").splitlines()
        pinned = (tmp_path / name).read_text(encoding="utf-8").splitlines()
        changed = [pair for pair in zip(source, pinned, strict=True) if pair[0] != pair[1]]
        assert len(changed) == 1


def test_the_repository_scripts_default_to_main() -> None:
    assert "{ 'main' }" in (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "${TERMINAL_SETUP_REF:-main}" in (ROOT / "install.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2", "main", "v1.2.3-rc1", ""])
def test_a_tag_that_is_not_a_release_is_refused(tag: str) -> None:
    with pytest.raises(PIN.PinError, match=r"is not vX\.Y\.Z"):
        PIN.pinned_text("install.sh", "${TERMINAL_SETUP_REF:-main}", tag)


@pytest.mark.parametrize("copies", [0, 2])
def test_a_script_without_exactly_one_default_ref_is_refused(copies: int) -> None:
    text = "ref=${TERMINAL_SETUP_REF:-main}\n" * copies

    with pytest.raises(PIN.PinError, match=f"holds {copies} copies"):
        PIN.pinned_text("install.sh", text, "v1.2.3")


def test_the_command_line_names_a_refusal_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert PIN.main(["--tag", "main", "--out", str(tmp_path)]) == 1
    assert "is not vX.Y.Z" in capsys.readouterr().err
