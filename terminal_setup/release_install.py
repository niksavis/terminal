from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import platform
import re
import shutil
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import typing
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
PREFETCH_WORKERS = 32
PROBE_URLS = (
    "https://github.com/niksavis/terminal/releases/latest/download/install.sh",
    "https://api.github.com/",
)
PROBE_TIMEOUT = 5
LOOKUP_TIMEOUT = 20
_PREFETCHED: dict[str, str] = {}
_UNREACHED: dict[str, Exception] = {}
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


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


def candidate_assets(assets: list[dict], patterns: list[str], machine: str) -> list[dict]:
    aliases = ARCH_ALIASES.get(machine)
    if aliases is None:
        raise InstallError(f"no release binary for this CPU ({machine})")
    candidates: list[dict] = []
    for pattern in patterns:
        for alias in aliases:
            wanted = re.compile(pattern.replace("{arch}", re.escape(alias)))
            candidates.extend(
                asset
                for asset in assets
                if wanted.fullmatch(asset.get("name", "")) and asset not in candidates
            )
    if not candidates:
        names = ", ".join(asset.get("name", "") for asset in assets)
        raise InstallError(f"no release asset matches {patterns} for {machine}; assets: {names}")
    return candidates


def select_asset(assets: list[dict], patterns: list[str], machine: str) -> dict:
    return candidate_assets(assets, patterns, machine)[0]


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


def starts(binary: Path) -> bool:
    try:
        subprocess.run(  # nosec B603
            [str(binary), "--version"], capture_output=True, timeout=30, check=False
        )
    except OSError:
        return False
    except subprocess.TimeoutExpired:
        return True
    return True


def install(destination: Path, content: bytes) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.stem}.", suffix=destination.suffix
    )
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    staged = Path(temporary)
    staged.chmod(0o755)
    if not starts(staged):
        staged.unlink()
        return False
    staged.replace(destination)
    return True


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


class _StopAtTag(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # noqa: PLR0913
        self,
        req: urllib.request.Request,
        fp: typing.IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if "/releases/tag/" in urllib.parse.urlsplit(newurl).path:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def latest_release_url(url: str) -> str:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "terminal-setup"})
    opener = urllib.request.build_opener(_StopAtTag)
    try:
        with opener.open(request, timeout=LOOKUP_TIMEOUT) as response:  # nosec B310
            return response.geturl()
    except urllib.error.HTTPError as error:
        location = error.headers.get("Location", "") if error.code in _REDIRECTS else ""
        error.close()
        if not location:
            raise
        return urllib.parse.urljoin(error.url, location)


def latest_tag(repo: str) -> str:
    final = latest_release_url(f"https://github.com/{repo}/releases/latest")
    _, marker, tag = final.partition("/releases/tag/")
    if not marker or not tag:
        raise InstallError(f"{repo}: could not read the latest release from {final}")
    return urllib.parse.unquote(tag)


def _prefetch_one(repo: str) -> tuple[str, str, Exception | None]:
    try:
        return repo, latest_tag(repo), None
    except (InstallError, OSError) as error:
        return repo, "", error


class _Trail(urllib.request.HTTPRedirectHandler):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def redirect_request(  # noqa: PLR0913
        self,
        req: urllib.request.Request,
        fp: typing.IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        self.url = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _probe_one(url: str) -> str:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "terminal-setup"})
    trail = _Trail(url)
    try:
        with urllib.request.build_opener(trail).open(  # nosec B310
            request, timeout=PROBE_TIMEOUT
        ):
            return ""
    except urllib.error.HTTPError as error:
        error.close()
        return ""
    except (OSError, http.client.HTTPException) as error:
        reason = _one_line(str(getattr(error, "reason", None) or error)) or type(error).__name__
        return f"{urllib.parse.urlsplit(trail.url).hostname} ({reason})"


def unreachable_reason() -> str:
    with ThreadPoolExecutor(max_workers=len(PROBE_URLS)) as pool:
        failed = [host for host in pool.map(_probe_one, PROBE_URLS) if host]
    if not failed:
        return ""
    return (
        f"cannot reach {', '.join(failed)} within {PROBE_TIMEOUT} s, so setup skips the "
        "GitHub release tools. Likely causes: a proxy that needs HTTPS_PROXY and NO_PROXY, "
        "a VPN, or the WSL networking mode. Check with: curl -sSIL "
        f"{PROBE_URLS[0]} in the same shell. Run terminal update again when it works."
    )


@contextmanager
def prefetched(repos: list[str]) -> Iterator[str]:
    unique = sorted(set(repos))
    reason = unreachable_reason() if unique else ""
    if reason:
        _UNREACHED.update((repo, InstallError(reason)) for repo in unique)
    elif unique:
        with ThreadPoolExecutor(max_workers=min(PREFETCH_WORKERS, len(unique))) as pool:
            for repo, tag, error in pool.map(_prefetch_one, unique):
                if tag:
                    _PREFETCHED[repo] = tag
                elif error is not None:
                    _UNREACHED[repo] = error
    try:
        yield reason
    finally:
        _PREFETCHED.clear()
        _UNREACHED.clear()


def _tag_of(repo: str) -> str:
    if (error := _UNREACHED.get(repo)) is not None:
        raise error
    return _PREFETCHED.pop(repo, "") or latest_tag(repo)


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
    tag = _tag_of(repo)
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
    candidates = candidate_assets(release.get("assets", []), patterns, platform.machine())
    for asset in candidates:
        url = asset.get("browser_download_url", "")
        if not url.startswith(f"https://github.com/{repo}/releases/download/"):
            raise InstallError(f"refusing a download outside {repo}'s releases: {url}")
        payload = verified(fetch(url), asset.get("digest") or "")
        if install(destination, extract(asset["name"], payload, binary)):
            record(binary, latest, bin_dir, state_dir)
            return f"installed {binary} {latest} into {destination}"
    names = ", ".join(asset["name"] for asset in candidates)
    raise InstallError(f"no release asset of {tag} starts on this machine; tried: {names}")


def check(
    repo: str, binary: str, bin_dir: Path | None = None, state_dir: Path | None = None
) -> tuple[str, str]:
    bin_dir = BIN_DIR if bin_dir is None else bin_dir
    state_dir = STATE_DIR if state_dir is None else state_dir
    tag = _tag_of(repo)
    latest = version_of(tag)
    if not latest:
        raise InstallError(f"{repo}: the latest release tag {tag!r} holds no version")
    current = current_version(binary, bin_dir, state_dir)
    if not current:
        return "missing", f"{binary} is not installed; {latest} is available"
    if current == latest:
        return "current", f"{binary} {current} is up to date"
    return "stale", f"{binary} {current} is installed; {latest} is available"


def _presence_line(job: dict[object, object], binary: str) -> str | None:
    if (BIN_DIR / binary).is_file():
        return None
    system = shutil.which(binary)
    if job.get("present_only") is True and system is None:
        return f"absent\t{binary}\t{binary} is not installed"
    if job.get("keep_system") is True and system:
        return f"skip\t{binary}\t{binary} has a system copy; setup leaves it as it is"
    return None


def _batch_line(job: object) -> str:
    if not isinstance(job, dict):
        return "fail\t?\ta batch job must be an object"
    binary = str(job.get("binary", ""))
    repo = str(job.get("repo", ""))
    patterns = job.get("patterns")
    if not binary or not REPO.fullmatch(repo) or not isinstance(patterns, list):
        return f"fail\t{binary or '?'}\tREPO must be OWNER/NAME on GitHub, got {repo!r}"
    if (presence := _presence_line(job, binary)) is not None:
        return presence
    try:
        if job.get("check") is True:
            status, message = check(repo, binary)
        else:
            status = "ok"
            message = run(repo, binary, job.get("update") is True, [str(p) for p in patterns])
    except InstallError as error:
        return f"fail\t{binary}\t{_one_line(str(error))}"
    except OSError as error:
        return f"fail\t{binary}\tdownload failed: {_one_line(str(error))}"
    return f"{status}\t{binary}\t{_one_line(message)}"


def _one_line(text: str) -> str:
    return " ".join(text.split())


UNREACHED = "unreached"
OFFLINE = "offline"


def run_batch(jobs: list[object]) -> list[str]:
    repos = [
        str(job.get("repo", ""))
        for job in jobs
        if isinstance(job, dict) and _presence_line(job, str(job.get("binary", ""))) is None
    ]
    with prefetched([repo for repo in repos if REPO.fullmatch(repo)]) as reason:
        if not reason:
            return [_batch_line(job) for job in jobs]
        return [f"{OFFLINE}\t\t{_one_line(reason)}"] + [
            _unreached_line(job) if isinstance(job, dict) else _batch_line(job) for job in jobs
        ]


def _unreached_line(job: dict[object, object]) -> str:
    binary = str(job.get("binary", ""))
    if (presence := _presence_line(job, binary)) is not None:
        return presence
    return f"{UNREACHED}\t{binary}\tskipped, because GitHub is unreachable"


def _batch_main(argv: list[str]) -> int:
    try:
        jobs = json.loads(argv[1]) if len(argv) == 2 else None
    except ValueError:
        jobs = None
    if not isinstance(jobs, list):
        print("usage: release_install.py --batch JSON-LIST-OF-JOBS", file=sys.stderr)
        return 2
    for line in run_batch(jobs):
        print(line, flush=True)
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--batch"]:
        return _batch_main(argv)
    if len(argv) < 4 or argv[2] not in {"0", "1"}:
        print("usage: release_install.py REPO BINARY 0|1 PATTERN [PATTERN ...]", file=sys.stderr)
        return 2
    if not REPO.fullmatch(argv[0]):
        print(f"{argv[1]}: REPO must be OWNER/NAME on GitHub, got {argv[0]!r}", file=sys.stderr)
        print("usage: release_install.py REPO BINARY 0|1 PATTERN [PATTERN ...]", file=sys.stderr)
        return 2
    try:
        with prefetched([argv[0]]):
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
