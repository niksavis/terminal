from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import prerequisites, windows_node
from terminal_setup.release_install import InstallError

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

VERSION = "v26.10.0"
NAME = f"node-{VERSION}-win-x64.zip"
ROOT = f"node-{VERSION}-win-x64/"


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _dist(payload: bytes, *, digest: str | None = None) -> dict[str, bytes]:
    sums = f"{digest or hashlib.sha256(payload).hexdigest()}  {NAME}\n"
    return {
        f"{windows_node.NODE_DIST}/index.json": json.dumps([
            {"version": "v27.0.0"},
            {"version": VERSION},
            {"version": "v26.9.0"},
        ]).encode(),
        f"{windows_node.NODE_DIST}/{VERSION}/SHASUMS256.txt": sums.encode(),
        f"{windows_node.NODE_DIST}/{VERSION}/{NAME}": payload,
    }


def test_latest_version_picks_the_newest_release_of_the_major() -> None:
    with mock.patch.object(windows_node, "fetch", side_effect=_dist(b"").__getitem__):
        assert windows_node.latest_version("26") == VERSION


def test_latest_version_refuses_a_missing_major() -> None:
    with (
        mock.patch.object(windows_node, "fetch", side_effect=_dist(b"").__getitem__),
        pytest.raises(InstallError, match="v25"),
    ):
        windows_node.latest_version("25")


@pytest.mark.parametrize(
    ("machine", "name"),
    [("AMD64", NAME), ("ARM64", f"node-{VERSION}-win-arm64.zip")],
)
def test_archive_name_maps_the_windows_cpu(machine: str, name: str) -> None:
    assert windows_node.archive_name(VERSION, machine) == name


def test_archive_name_refuses_an_unknown_cpu() -> None:
    with pytest.raises(InstallError, match="x86"):
        windows_node.archive_name(VERSION, "x86")


def test_install_extracts_the_verified_archive(tmp_path: Path) -> None:
    payload = _zip({f"{ROOT}node.exe": b"node", f"{ROOT}node_modules/npm/a.js": b"npm"})
    target = tmp_path / "nodejs"

    with mock.patch.object(windows_node, "fetch", side_effect=_dist(payload).__getitem__):
        windows_node.install(VERSION, "AMD64", target)

    assert (target / "node.exe").read_bytes() == b"node"
    assert (target / "node_modules" / "npm" / "a.js").read_bytes() == b"npm"


def test_install_keeps_global_packages_beside_node(tmp_path: Path) -> None:
    target = tmp_path / "nodejs"
    (target / "node_modules" / "@openai" / "codex").mkdir(parents=True)
    (target / "codex.cmd").write_text("shim", encoding="utf-8")
    payload = _zip({f"{ROOT}node.exe": b"node"})

    with mock.patch.object(windows_node, "fetch", side_effect=_dist(payload).__getitem__):
        windows_node.install(VERSION, "AMD64", target)

    assert (target / "codex.cmd").read_text(encoding="utf-8") == "shim"
    assert (target / "node_modules" / "@openai" / "codex").is_dir()


def test_install_refuses_a_checksum_mismatch(tmp_path: Path) -> None:
    payload = _zip({f"{ROOT}node.exe": b"node"})

    with (
        mock.patch.object(
            windows_node, "fetch", side_effect=_dist(payload, digest="0" * 64).__getitem__
        ),
        pytest.raises(InstallError, match="checksum mismatch"),
    ):
        windows_node.install(VERSION, "AMD64", tmp_path / "nodejs")

    assert not (tmp_path / "nodejs").exists()


def test_extract_refuses_an_entry_that_leaves_the_target(tmp_path: Path) -> None:
    payload = _zip({f"{ROOT}../evil.txt": b"x"})

    with pytest.raises(InstallError, match="leaves"):
        windows_node.extract_into(payload, ROOT, tmp_path / "nodejs")

    assert not (tmp_path / "evil.txt").exists()


def test_replace_file_moves_a_locked_file_aside(tmp_path: Path) -> None:
    destination = tmp_path / "node.exe"
    destination.write_bytes(b"old")
    real_replace = Path.replace
    calls: list[Path] = []

    def locked_once(self: Path, target: Path) -> Path:
        calls.append(Path(target))
        if len(calls) == 1:
            raise PermissionError("the file is in use")
        return real_replace(self, target)

    with mock.patch.object(Path, "replace", locked_once):
        windows_node.replace_file(destination, b"new")

    assert destination.read_bytes() == b"new"
    stale = list(tmp_path.glob(f".node.exe.*{windows_node.STALE_SUFFIX}"))
    assert [path.read_bytes() for path in stale] == [b"old"]


def test_remove_stale_deletes_moved_aside_files(tmp_path: Path) -> None:
    stale = tmp_path / f".node.exe.abc{windows_node.STALE_SUFFIX}"
    stale.write_bytes(b"old")

    windows_node.remove_stale(tmp_path)

    assert not stale.exists()


class NodeRunner(RecordingRunner):
    node_path: str | None = None

    def which(self, command: str) -> str | None:
        return self.node_path if command == "node" else None


def _node_runner(path: str | None, version: str = "", *, dry_run: bool = False) -> NodeRunner:
    runner = NodeRunner(reporter=CapturingReporter(), dry_run=dry_run)
    runner.node_path = path
    if path is not None:
        runner.outputs[(path, "--version")] = (0, version)
    return runner


def _ensure(runner: NodeRunner, tmp_path: Path, *, update: bool = False) -> mock.MagicMock:
    platform = replace(_windows_platform(), home=tmp_path)
    with (
        mock.patch.object(prerequisites.windows_node, "latest_version", return_value=VERSION),
        mock.patch.object(prerequisites.windows_node, "install") as install,
        mock.patch.object(prerequisites, "_add_to_process_path"),
    ):
        prerequisites._ensure_node_windows(runner, platform, update=update)
    return install


def _managed(tmp_path: Path) -> str:
    return str(replace(_windows_platform(), home=tmp_path).user_programs_dir / "nodejs" / "node")


def test_windows_node_skips_a_present_node_of_the_target_major(tmp_path: Path) -> None:
    runner = _node_runner("C:/Program Files/nodejs/node.exe", "v26.1.0\n")

    install = _ensure(runner, tmp_path, update=True)

    install.assert_not_called()


def test_windows_node_installs_when_missing_and_adds_the_path(tmp_path: Path) -> None:
    runner = _node_runner(None)

    install = _ensure(runner, tmp_path)

    install.assert_called_once()
    assert install.call_args.args[0] == VERSION
    assert any(command[0] == "powershell" for command in runner.commands)


def test_windows_node_replaces_an_older_node_and_names_it(tmp_path: Path) -> None:
    runner = _node_runner("C:/Program Files/nodejs/node.exe", "v22.3.0\n")

    install = _ensure(runner, tmp_path)

    install.assert_called_once()
    assert any(
        level == "warn" and "C:/Program Files/nodejs/node.exe" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


@pytest.mark.parametrize(("installed", "installs"), [("v26.10.0\n", False), ("v26.9.0\n", True)])
def test_windows_node_update_compares_the_managed_node_with_the_latest(
    tmp_path: Path, installed: str, *, installs: bool
) -> None:
    runner = _node_runner(_managed(tmp_path), installed)

    install = _ensure(runner, tmp_path, update=True)

    assert install.called is installs


def test_windows_node_dry_run_installs_nothing(tmp_path: Path) -> None:
    runner = _node_runner(None, dry_run=True)

    install = _ensure(runner, tmp_path)

    install.assert_not_called()
    assert runner.commands == []
