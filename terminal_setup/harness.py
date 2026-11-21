from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGED_NAME = "_harness.json"
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_PACKAGE = Path(__file__).resolve().parent


class HarnessVersionError(RuntimeError):
    pass


def harness_file(package: Path = _PACKAGE) -> Path:
    packaged = package / PACKAGED_NAME
    if packaged.is_file():
        return packaged
    return package.parent / ".basicly" / "state" / "install.json"


def harness_version(package: Path = _PACKAGE) -> str:
    source = harness_file(package)
    expected = 'a JSON object with "basicly_version" set to MAJOR.MINOR.PATCH, such as "0.47.1"'
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        message = (
            f"the basicly harness version is missing: neither {package / PACKAGED_NAME} "
            f"nor {source} exists. Reinstall terminal, or run basicly install in the clone."
        )
        raise HarnessVersionError(message) from None
    except (OSError, ValueError) as error:
        message = (
            f"the basicly harness version in {source} cannot be read ({error}); "
            f"expected {expected}."
        )
        raise HarnessVersionError(message) from None
    version = data.get("basicly_version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not _VERSION.match(version):
        message = f"the basicly harness version in {source} is {version!r}; expected {expected}."
        raise HarnessVersionError(message)
    return version


def basicly_ref(package: Path = _PACKAGE) -> str:
    return f"v{harness_version(package)}"


def basicly_spec(package: Path = _PACKAGE) -> str:
    version = harness_version(package)
    return (
        "https://github.com/niksavis/basicly/releases/download/"
        f"v{version}/basicly-{version}-py3-none-any.whl"
    )
