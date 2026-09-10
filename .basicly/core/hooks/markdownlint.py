"""Run markdownlint-cli2 through a node this script resolves itself (basicly-jr0l.14).

The hook used to be ``npx --no-install markdownlint-cli2``, which depends on the
ambient ``PATH`` having a usable node. A headless agent's shell does not: login and
interactive shells source a profile that puts nvm's ``bin`` first, scripts and hooks
do not, and WSL interop then resolves ``node``/``npx`` to a Windows install under
``/mnt/c``. What that costs varies by machine and reads as flaky either way — a
worktree here fails in under a second with

    CMD.EXE was started with the above path as the current directory.
    UNC paths are not supported.  Defaulting to Windows directory.
    'markdownlint-cli2' is not recognized as an internal or external command

while the machine in the original report stalled past ten minutes on the first
commit in a fresh worktree. Every lane pays it once, and to the StallWatchdog a
lane parked on this looks exactly like a wedged one: neither HEAD nor the dirty
tree moves.

The repo already documented the workaround — prepend nvm's bin before running npx
from a script (``skills/node/references/wsl-node-path.md``). That is guidance, and
guidance is the half that does not bind on the case that matters, because the agent
that most needs it is the one least able to apply it. So the rule becomes a hook:
resolve the interpreter here, deterministically, and never invoke ``npx`` at all.

Two failure modes are deliberately loud rather than slow. No usable node, and no
installed ``markdownlint-cli2``, each exit 1 with one line naming what to do — a
consumer who has neither is told so in a second instead of learning it from a
timeout.

stdlib only, by the hooks convention: no dependency ships to consumers.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path, PurePath

# markdownlint-cli2's real entry point inside node_modules. Invoked directly with
# a resolved node, which is what removes npx — and with it the Windows npx — from
# the path entirely. The `.bin` shim beside it is no use here: it carries a
# `#!/usr/bin/env node` shebang and so needs the very interpreter we are resolving.
_CLI_ENTRY = Path("node_modules") / "markdownlint-cli2" / "markdownlint-cli2-bin.mjs"

# Where a Linux node lives when it is not on PATH. nvm first because that is what
# this repo's contributors use, then the distro locations.
_NVM_ROOTS = ("versions/node",)
_SYSTEM_NODES = (Path("/usr/local/bin/node"), Path("/usr/bin/node"))


def _is_windows_interop(candidate: PurePath) -> bool:
    r"""True when *candidate* is a Windows binary reached through WSL interop.

    Only meaningful on Linux. A path under ``/mnt`` there is the Windows drive
    mount, and running it hands the job to CMD.EXE, which cannot even express the
    worktree's ``\\wsl.localhost\...`` directory. On a real Windows host a Windows
    path is simply where node lives, so the rule must not apply.

    Read from the path's POSIX text rather than its ``parts``, because ``parts``
    is a property of the *host's* path flavour and not of the path: a Windows
    interpreter parses ``/mnt/c/...`` as a rootless ``WindowsPath`` whose anchor
    is ``\\`` and which ``is_absolute()`` calls False, so the rule could not even
    be exercised there (basicly-jr0l.23). The interop path is a fact about the
    string, so the check is too — which also makes it assertable on every OS leg.

    Typed :class:`PurePath` for the same reason, and it is not a widening for its
    own sake: it lets a test hand this the *other* flavour deliberately, so the
    windows-only failure is reproducible on any host instead of only on the runner
    that has one.
    """
    posix = candidate.as_posix()
    return sys.platform == "linux" and (posix == "/mnt" or posix.startswith("/mnt/"))


def _version_key(directory: Path) -> tuple[int, ...]:
    """Sort key for an nvm version directory, numerically rather than lexically.

    ``tail -1`` picks v9 over v10; the reference doc this replaces flagged that as
    a caveat for a human to remember, which is exactly the kind of thing to settle
    in code.
    """
    parts = directory.name.lstrip("v").split(".")
    return tuple(int(part) if part.isdigit() else 0 for part in parts)


def _nvm_nodes() -> list[Path]:
    """Every node under an nvm install, newest version first."""
    nvm_dir = Path(os.environ.get("NVM_DIR") or Path.home() / ".nvm")
    found: list[Path] = []
    for relative in _NVM_ROOTS:
        root = nvm_dir / relative
        if not root.is_dir():
            continue
        found += sorted((d for d in root.iterdir() if d.is_dir()), key=_version_key, reverse=True)
    return [d / "bin" / "node" for d in found]


def find_node() -> Path | None:
    """A usable node interpreter, or None when the machine has none.

    PATH first so an explicitly chosen node wins, but a Windows interop hit is
    skipped rather than accepted — that resolution is the defect, not a fallback.
    """
    on_path = shutil.which("node")
    if on_path and not _is_windows_interop(Path(on_path)):
        return Path(on_path)
    for candidate in (*_nvm_nodes(), *_SYSTEM_NODES):
        if candidate.is_file() and not _is_windows_interop(candidate):
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    """Lint with a resolved node; 1 with one actionable line when that is impossible."""
    args = list(argv if argv is not None else sys.argv[1:])
    if not _CLI_ENTRY.is_file():
        print(
            f"markdownlint: {_CLI_ENTRY} is missing — run `npm install` "
            "(worktree provisioning does this for you)",
            file=sys.stderr,
        )
        return 1
    node = find_node()
    if node is None:
        print(
            "markdownlint: no usable node found on PATH, under nvm, or in "
            "/usr/bin — install node (nvm install --lts) so the markdown gate "
            "can run; a Windows node reached through /mnt is deliberately not used",
            file=sys.stderr,
        )
        return 1
    return subprocess.run([str(node), str(_CLI_ENTRY), *args], check=False).returncode  # nosec B603


if __name__ == "__main__":
    sys.exit(main())
