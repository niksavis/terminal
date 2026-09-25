from __future__ import annotations

import ast
import hashlib
import io
import json
import tarfile
import zipfile
from email.message import Message
from pathlib import Path
from typing import Literal

import pytest

from terminal_setup import release_install
from terminal_setup.prerequisites import RELEASE_TOOLS

ASSETS_SEEN_2026_09_25 = {
    "fd-find": (
        "fd-v10.5.0-x86_64-unknown-linux-gnu.tar.gz",
        "fd-v10.5.0-x86_64-unknown-linux-musl.tar.gz",
        "fd-v10.5.0-aarch64-unknown-linux-gnu.tar.gz",
    ),
    "bat": (
        "bat-v0.26.1-x86_64-unknown-linux-gnu.tar.gz",
        "bat-v0.26.1-x86_64-unknown-linux-musl.tar.gz",
        "bat-v0.26.1-aarch64-unknown-linux-musl.tar.gz",
    ),
    "ripgrep": (
        "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz",
        "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz.sha256",
        "ripgrep-15.2.0-aarch64-unknown-linux-gnu.tar.gz",
    ),
    "xh": (
        "xh-v0.26.2-x86_64-unknown-linux-musl.tar.gz",
        "xh-v0.26.2-aarch64-unknown-linux-musl.tar.gz",
    ),
    "ast-grep": ("app-x86_64-unknown-linux-gnu.zip", "app-aarch64-unknown-linux-gnu.zip"),
    "sd": (
        "sd-v1.1.0-x86_64-unknown-linux-gnu.tar.gz",
        "sd-v1.1.0-x86_64-unknown-linux-musl.tar.gz",
        "sd-v1.1.0-aarch64-unknown-linux-musl.tar.gz",
    ),
    "just": (
        "just-1.58.0-x86_64-unknown-linux-musl.tar.gz",
        "SHA256SUMS",
        "just-1.58.0-aarch64-unknown-linux-musl.tar.gz",
    ),
    "git-delta": (
        "delta-0.19.2-x86_64-unknown-linux-gnu.tar.gz",
        "delta-0.19.2-x86_64-unknown-linux-musl.tar.gz",
        "delta-0.19.2-aarch64-unknown-linux-gnu.tar.gz",
    ),
    "typos": (
        "typos-v1.50.2-x86_64-unknown-linux-musl.tar.gz",
        "typos-v1.50.2-aarch64-unknown-linux-musl.tar.gz",
    ),
    "fzf": ("fzf-0.74.4-linux_amd64.tar.gz", "fzf-0.74.4-linux_arm64.tar.gz"),
    "jq": ("jq-linux-amd64", "jq-linux-arm64", "sha256sum.txt"),
    "yq": ("yq_linux_amd64", "yq_linux_amd64.tar.gz", "yq_linux_arm64"),
    "shellcheck": (
        "shellcheck-v0.11.0.linux.x86_64.tar.gz",
        "shellcheck-v0.11.0.linux.x86_64.tar.xz",
        "shellcheck-v0.11.0.linux.aarch64.tar.xz",
    ),
    "git-lfs": ("git-lfs-linux-amd64-v3.8.0.tar.gz", "git-lfs-linux-arm64-v3.8.0.tar.gz"),
    "direnv": ("direnv.linux-amd64", "direnv.linux-arm64"),
}
EXPECTED_X86_64 = {
    "fd-find": "fd-v10.5.0-x86_64-unknown-linux-musl.tar.gz",
    "bat": "bat-v0.26.1-x86_64-unknown-linux-musl.tar.gz",
    "ripgrep": "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz",
    "xh": "xh-v0.26.2-x86_64-unknown-linux-musl.tar.gz",
    "ast-grep": "app-x86_64-unknown-linux-gnu.zip",
    "sd": "sd-v1.1.0-x86_64-unknown-linux-musl.tar.gz",
    "just": "just-1.58.0-x86_64-unknown-linux-musl.tar.gz",
    "git-delta": "delta-0.19.2-x86_64-unknown-linux-musl.tar.gz",
    "typos": "typos-v1.50.2-x86_64-unknown-linux-musl.tar.gz",
    "fzf": "fzf-0.74.4-linux_amd64.tar.gz",
    "jq": "jq-linux-amd64",
    "yq": "yq_linux_amd64",
    "shellcheck": "shellcheck-v0.11.0.linux.x86_64.tar.xz",
    "git-lfs": "git-lfs-linux-amd64-v3.8.0.tar.gz",
    "direnv": "direnv.linux-amd64",
}


def _assets(names: tuple[str, ...]) -> list[dict]:
    return [{"name": name} for name in names]


def test_the_script_parses_as_python_3_12_which_ubuntu_24_04_ships() -> None:
    source = Path(release_install.__file__).read_text(encoding="utf-8")

    ast.parse(source, feature_version=(3, 12))


def test_every_release_tool_has_an_asset_fixture() -> None:
    assert sorted(ASSETS_SEEN_2026_09_25) == sorted(RELEASE_TOOLS)


@pytest.mark.parametrize("package", sorted(RELEASE_TOOLS))
def test_each_tool_selects_its_x86_64_asset_preferring_musl(package: str) -> None:
    patterns = list(RELEASE_TOOLS[package][2])
    asset = release_install.select_asset(
        _assets(ASSETS_SEEN_2026_09_25[package]), patterns, "x86_64"
    )

    assert asset["name"] == EXPECTED_X86_64[package]


@pytest.mark.parametrize("package", sorted(RELEASE_TOOLS))
def test_each_tool_selects_an_arm64_asset(package: str) -> None:
    patterns = list(RELEASE_TOOLS[package][2])
    asset = release_install.select_asset(
        _assets(ASSETS_SEEN_2026_09_25[package]), patterns, "aarch64"
    )

    assert "aarch64" in asset["name"] or "arm64" in asset["name"]


def test_select_asset_refuses_an_unknown_cpu_by_name() -> None:
    with pytest.raises(release_install.InstallError, match="riscv64"):
        release_install.select_asset(_assets(("jq-linux-amd64",)), ["jq-linux-{arch}"], "riscv64")


def test_verified_refuses_a_checksum_mismatch() -> None:
    with pytest.raises(release_install.InstallError, match="checksum mismatch"):
        release_install.verified(b"payload", "sha256:" + "0" * 64)


def test_verified_refuses_an_asset_without_a_digest() -> None:
    with pytest.raises(release_install.InstallError, match="no sha256 digest"):
        release_install.verified(b"payload", "")


def test_verified_accepts_the_matching_digest() -> None:
    digest = "sha256:" + hashlib.sha256(b"payload").hexdigest()

    assert release_install.verified(b"payload", digest) == b"payload"


def _tar(member: str, content: bytes, mode: Literal["w:gz", "w:xz"]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        info = tarfile.TarInfo(member)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_extract_finds_the_binary_in_each_archive_kind() -> None:
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("ast-grep", b"zip")

    assert release_install.extract("a.tar.gz", _tar("fd-v1/fd", b"gz", "w:gz"), "fd") == b"gz"
    assert (
        release_install.extract("a.tar.xz", _tar("s/shellcheck", b"xz", "w:xz"), "shellcheck")
        == b"xz"
    )
    assert release_install.extract("app.zip", zipped.getvalue(), "ast-grep") == b"zip"
    assert release_install.extract("jq-linux-amd64", b"raw", "jq") == b"raw"


def test_extract_refuses_an_archive_without_the_binary() -> None:
    with pytest.raises(release_install.InstallError, match="no file named rg"):
        release_install.extract("a.tar.gz", _tar("fd-v1/fd", b"gz", "w:gz"), "rg")


def _release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installed: str) -> list[str]:
    content = b"#!/bin/sh\n"
    release = {
        "tag_name": "v2.0.0",
        "assets": [
            {
                "name": "jq-linux-amd64",
                "browser_download_url": "https://github.com/jqlang/jq/releases/download/v2.0.0/jq-linux-amd64",
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return json.dumps(release).encode() if "api.github.com" in url else content

    monkeypatch.setattr(release_install, "fetch", fetch)
    monkeypatch.setattr(release_install, "latest_tag", lambda _repo: release["tag_name"])
    monkeypatch.setattr(release_install, "BIN_DIR", tmp_path)
    monkeypatch.setattr(release_install, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(release_install, "installed_version", lambda _path: installed)
    monkeypatch.setattr(release_install.platform, "machine", lambda: "x86_64")
    return fetched


def test_run_skips_a_tool_at_the_latest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = _release(tmp_path, monkeypatch, "2.0.0")

    message = release_install.run("jqlang/jq", "jq", False, ["jq-linux-{arch}"])

    assert message == "jq 2.0.0 is up to date"
    assert fetched == []


def test_run_names_the_update_flag_for_an_older_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _release(tmp_path, monkeypatch, "1.0.0")

    message = release_install.run("jqlang/jq", "jq", False, ["jq-linux-{arch}"])

    assert message == "jq 1.0.0 is installed; 2.0.0 is available: rerun with --update"
    assert not (tmp_path / "jq").exists()


@pytest.mark.parametrize(("installed", "update"), [("", False), ("1.0.0", True)])
def test_run_installs_a_missing_tool_or_updates_on_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installed: str, *, update: bool
) -> None:
    _release(tmp_path, monkeypatch, installed)

    message = release_install.run("jqlang/jq", "jq", update, ["jq-linux-{arch}"])

    assert message == f"installed jq 2.0.0 into {tmp_path / 'jq'}"
    assert (tmp_path / "jq").read_bytes() == b"#!/bin/sh\n"


def test_main_refuses_bad_arguments_with_the_usage() -> None:
    assert release_install.main(["jqlang/jq", "jq", "yes", "jq-linux-{arch}"]) == 2


def test_a_binary_that_misreports_its_version_is_up_to_date_after_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _release(tmp_path, monkeypatch, "1.0.0")

    release_install.run("jqlang/jq", "jq", True, ["jq-linux-{arch}"])
    message = release_install.run("jqlang/jq", "jq", False, ["jq-linux-{arch}"])

    assert message == "jq 2.0.0 is up to date"


def test_the_record_is_ignored_once_the_binary_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _release(tmp_path, monkeypatch, "1.0.0")
    release_install.run("jqlang/jq", "jq", True, ["jq-linux-{arch}"])
    monkeypatch.setattr(release_install, "installed_version", lambda _path: "1.5.0")

    message = release_install.run("jqlang/jq", "jq", False, ["jq-linux-{arch}"])

    assert message == "jq 1.5.0 is installed; 2.0.0 is available: rerun with --update"


def test_a_rate_limited_api_names_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def limited(url: str) -> bytes:
        raise release_install.urllib.error.HTTPError(
            url, 403, "rate limit exceeded", Message(), None
        )

    monkeypatch.setattr(release_install, "fetch", limited)

    with pytest.raises(release_install.InstallError, match="GITHUB_TOKEN"):
        release_install.release_of("jqlang/jq", "jq-1.8.2")


def test_run_refuses_a_download_outside_the_repositorys_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _release(tmp_path, monkeypatch, "")
    original = release_install.release_of

    def moved(repo: str, tag: str) -> dict:
        release = original(repo, tag)
        release["assets"][0]["browser_download_url"] = "https://evil.invalid/jq"
        return release

    monkeypatch.setattr(release_install, "release_of", moved)

    with pytest.raises(release_install.InstallError, match="outside jqlang/jq's releases"):
        release_install.run("jqlang/jq", "jq", False, ["jq-linux-{arch}"])
    assert not (tmp_path / "jq").exists()
