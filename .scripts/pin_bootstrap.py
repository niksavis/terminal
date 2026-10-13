from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFS = {
    "install.ps1": "{{ '{ref}' }}",
    "install.sh": "${{TERMINAL_SETUP_REF:-{ref}}}",
}


class PinError(Exception):
    pass


def pinned_text(name: str, text: str, tag: str) -> str:
    if not TAG_PATTERN.fullmatch(tag):
        raise PinError(f"tag {tag!r} is not vX.Y.Z; run: pin_bootstrap.py --tag v1.2.3")
    template = DEFAULT_REFS[name]
    default = template.format(ref="main")
    count = text.count(default)
    if count != 1:
        raise PinError(f"{name} holds {count} copies of the default ref {default!r}; expected 1")
    return text.replace(default, template.format(ref=tag))


def pin(source_dir: Path, out_dir: Path, tag: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in DEFAULT_REFS:
        text = (source_dir / name).read_text(encoding="utf-8")
        destination = out_dir / name
        destination.write_text(pinned_text(name, text, tag), encoding="utf-8", newline="\n")
        written.append(destination)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write install.ps1 and install.sh with the default ref set to a release tag."
    )
    parser.add_argument("--tag", required=True, help="the release tag, for example v1.2.3")
    parser.add_argument("--out", required=True, type=Path, help="the directory to write into")
    args = parser.parse_args(argv)
    try:
        for path in pin(REPO_ROOT, args.out, args.tag):
            print(f"pinned {path} to {args.tag}")
    except PinError as error:
        print(f"pin_bootstrap: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
