from __future__ import annotations

import os
import sys
import time

import runner

from orch_pace import snapshot

WRITER = "statusline"
USAGE = "usage: orch-statusline-tap -- COMMAND [ARG...]"


def save(data: bytes, environ: dict[str, str]) -> None:
    try:
        snapshot.record(data, environ, int(time.time()), WRITER)
    except OSError, ValueError, RuntimeError, TypeError, KeyError, ArithmeticError:
        return


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--"]:
        args = args[1:]
    try:
        data = sys.stdin.buffer.read()
    except OSError, ValueError:
        data = b""
    environ = dict(os.environ)
    if not args:
        save(data, environ)
        print(f"orch-statusline-tap: no status line command given; {USAGE}", file=sys.stderr)
        return 2
    try:
        code, out = runner.relay(args, data, lambda: save(data, environ))
    except OSError as missing:
        save(data, environ)
        print(
            f"orch-statusline-tap: {args[0]} cannot start: {missing.strerror or missing}; {USAGE}",
            file=sys.stderr,
        )
        return 127
    sys.stdout.buffer.write(out)
    sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
