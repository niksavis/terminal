from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ARCH_ALIASES = {
    "x86_64": ("x86_64", "amd64"),
    "aarch64": ("aarch64", "arm64"),
    "AMD64": ("x86_64", "amd64"),
    "ARM64": ("aarch64", "arm64", "x86_64", "amd64"),
}
VERSION = re.compile(r"\d+(?:\.\d+)+")
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+")
BIN_DIR = Path.home() / ".local" / "bin"
STATE_DIR = Path.home() / ".local" / "share" / "terminal-setup" / "releases"


class InstallError(Exception):
    pass


def version_of(text: str) -> str:
    match = VERSION.search(text)
    return match.group(0) if match else ""


def installed_version(binary: Path) -> str:
    if not binary.is_file():
        return ""
    try:
        result = subprocess.run(  # nosec B603
            [str(binary), "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except OSError:
        return ""
    return version_of(result.stdout + result.stderr)


def current_version(binary: str, bin_dir: Path, state_dir: Path) -> str:
    reported = installed_version(bin_dir / binary)
    state = state_dir / binary
    if reported and state.is_file():
        tag, _, recorded = state.read_text(encoding="utf-8").strip().partition(" ")
        if recorded == reported:
            return tag
    return reported


def record(binary: str, tag: str, bin_dir: Path, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / binary).write_text(
        f"{tag} {installed_version(bin_dir / binary)}\n", encoding="utf-8"
    )


def select_asset(assets: list[dict], patterns: list[str], machine: str) -> dict:
    aliases = ARCH_ALIASES.get(machine)
    if aliases is None:
        raise InstallError(f"no release binary for this CPU ({machine})")
    for pattern in patterns:
        for alias in aliases:
            wanted = re.compile(pattern.replace("{arch}", re.escape(alias)))
            for asset in assets:
                if wanted.fullmatch(asset.get("name", "")):
                    return asset
    names = ", ".join(asset.get("name", "") for asset in assets)
    raise InstallError(f"no release asset matches {patterns} for {machine}; assets: {names}")


def verified(payload: bytes, digest: str) -> bytes:
    algorithm, _, expected = digest.partition(":")
    if algorithm != "sha256" or not expected:
        raise InstallError(f"the release asset has no sha256 digest ({digest!r}); refusing it")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise InstallError(f"checksum mismatch: expected {expected}, downloaded {actual}")
    return payload


def extract(name: str, payload: bytes, binary: str) -> bytes:
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.infolist():
                if not member.is_dir() and Path(member.filename).name == binary:
                    return archive.read(member)
    elif re.search(r"\.(tar\.gz|tgz|tar\.xz)$", name):
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            for member in archive.getmembers():
                if member.isfile() and Path(member.name).name == binary:
                    handle = archive.extractfile(member)
                    if handle is not None:
                        return handle.read()
    else:
        return payload
    raise InstallError(f"{name} holds no file named {binary}")


def install(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    Path(temporary).chmod(0o755)
    Path(temporary).replace(destination)


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise InstallError(f"refusing a non-https URL: {url}")
    accept = "application/vnd.github+json" if url.startswith("https://api.github.com/") else "*/*"
    headers = {"Accept": accept, "User-Agent": "terminal-setup"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
        return response.read()


def latest_tag(repo: str) -> str:
    request = urllib.request.Request(
        f"https://github.com/{repo}/releases/latest",
        method="HEAD",
        headers={"User-Agent": "terminal-setup"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
        final = response.geturl()
    _, marker, tag = final.partition("/releases/tag/")
    if not marker or not tag:
        raise InstallError(f"{repo}: could not read the latest release from {final}")
    return urllib.parse.unquote(tag)


class ReleaseAssets(HTMLParser):
    def __init__(self, repo: str, tag: str) -> None:
        super().__init__()
        self.prefix = (
            f"https://github.com/{repo}/releases/download/{urllib.parse.quote(tag, safe='')}/"
        )
        self.assets: list[dict[str, str]] = []
        self.asset: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "li":
            self.asset = {}
        elif tag == "a":
            url = urllib.parse.urljoin("https://github.com", attributes.get("href") or "")
            if url.startswith(self.prefix):
                self.asset.update(
                    name=urllib.parse.unquote(url.rsplit("/", 1)[-1]), browser_download_url=url
                )
        elif tag == "clipboard-copy":
            value = attributes.get("value") or ""
            if re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                self.asset["digest"] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "li":
            if "name" in self.asset:
                self.assets.append(self.asset)
            self.asset = {}


def public_release_of(repo: str, tag: str) -> dict:
    url = f"https://github.com/{repo}/releases/expanded_assets/{urllib.parse.quote(tag, safe='')}"
    parser = ReleaseAssets(repo, tag)
    parser.feed(fetch(url).decode("utf-8"))
    parser.close()
    if not parser.assets:
        raise InstallError(f"{repo}: the public release page for {tag!r} holds no download assets")
    return {"tag_name": tag, "assets": parser.assets}


def release_of(repo: str, tag: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    try:
        return json.loads(fetch(url))
    except urllib.error.HTTPError as error:
        if error.code == 429 or (
            error.code == 403
            and (
                error.headers.get("x-ratelimit-remaining") == "0"
                or error.headers.get("retry-after") is not None
                or b"rate limit" in error.read().lower()
            )
        ):
            return public_release_of(repo, tag)
        raise


def run(  # noqa: PLR0913
    repo: str,
    binary: str,
    update: bool,
    patterns: list[str],
    bin_dir: Path | None = None,
    state_dir: Path | None = None,
) -> str:
    bin_dir = BIN_DIR if bin_dir is None else bin_dir
    state_dir = STATE_DIR if state_dir is None else state_dir
    tag = latest_tag(repo)
    latest = version_of(tag)
    if not latest:
        raise InstallError(f"{repo}: the latest release tag {tag!r} holds no version")
    destination = bin_dir / binary
    current = current_version(binary, bin_dir, state_dir)
    if current == latest:
        return f"{binary} {current} is up to date"
    if current and not update:
        return f"{binary} {current} is installed; {latest} is available"
    release = release_of(repo, tag)
    asset = select_asset(release.get("assets", []), patterns, platform.machine())
    url = asset.get("browser_download_url", "")
    if not url.startswith(f"https://github.com/{repo}/releases/download/"):
        raise InstallError(f"refusing a download outside {repo}'s releases: {url}")
    payload = verified(fetch(url), asset.get("digest") or "")
    install(destination, extract(asset["name"], payload, binary))
    record(binary, latest, bin_dir, state_dir)
    return f"installed {binary} {latest} into {destination}"


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[2] not in {"0", "1"}:
        print("usage: release_install.py REPO BINARY 0|1 PATTERN [PATTERN ...]", file=sys.stderr)
        return 2
    if not REPO.fullmatch(argv[0]):
        print(f"{argv[1]}: REPO must be OWNER/NAME on GitHub, got {argv[0]!r}", file=sys.stderr)
        print("usage: release_install.py REPO BINARY 0|1 PATTERN [PATTERN ...]", file=sys.stderr)
        return 2
    try:
        print(run(argv[0], argv[1], argv[2] == "1", argv[3:]))
    except InstallError as error:
        print(f"{argv[1]}: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"{argv[1]}: download failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
