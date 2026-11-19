from __future__ import annotations

import importlib.util
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_init.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_push_guard = _load("vault_push_guard.py", "basicly_tracker_kit_vault_push_guard")

SUGGESTED_NAME = "backlog-vault"
FIX = 1
REFUSED = 2
NO_GENESIS = 8
PERMISSIONS = [
    "Private or public: whoever can read the vault reads every project in it; choose public "
    "only when every project in it is public.",
    "Give each team member write access to it; nobody needs rights on a code repository's main.",
    "Protect its main against force-push and deletion where your host offers it: GitHub offers "
    "a ruleset or branch protection on public repositories on every plan, and on private "
    "repositories only on Pro, Team or Enterprise (GitHub docs, read 2026-11-12); Bitbucket "
    "offers a branch restriction.",
    "On GitHub Free that means a private vault cannot be protected on the host and a public one "
    "can; you choose.",
    "The tracker checks the vault history itself and stops on a rewrite, with or without that.",
    "CI needs no access to the vault: CI never reads tracker records, and the local commit "
    "hook checks record ids.",
]

_README = """# Backlog vault

This repository holds the work records of one or more projects, written by the basicly tracker.

- `log/WRITER/NNNNN.jsonl`: each writer's events, one JSON object per line, never rewritten.
- `reader.py`: prints every record from these files with plain Python, no other tool needed.
- `FORMAT.md`: the line format.

To stop using it, remove `.basicly-tracker.toml` from each code repository,
then delete this repository.
"""

_FORMAT = """# Vault format 1

Each writer appends to its own files under `log/WRITER/`. A line is one JSON object with
`id`, `kind`, `record`, `writer`, `session` and `at`. The first valid claim of a record, in the
order of this repository's first-parent history, holds the record.
"""

_READER = """import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
records = {}
for path in sorted(root.glob("log/*/*.jsonl")):
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("record"):
            records.setdefault(event["record"], []).append(event["kind"])
for record, kinds in sorted(records.items()):
    print(record, " ".join(kinds))
"""

Runner = Callable[..., str]
_PROBE_ERRORS = (git_runner.GitRunnerError, vault_clone.CloneError)


def genesis_files() -> dict[str, str]:
    return {
        "vault.toml": 'format = 1\nkind = "vault"\n',
        "FORMAT.md": _FORMAT,
        "reader.py": _READER,
        "README.md": _README,
    }


def heads(url: str, allow_file: bool, runner: Runner, scratch: Path) -> list[str]:
    listed = runner(["ls-remote", git_runner.END_OF_OPTIONS, url], scratch, allow_file=allow_file)
    return [line for line in listed.splitlines() if line.strip()]


def guide(url: str) -> dict[str, object]:
    return {
        "vault": url,
        "suggested_name": SUGGESTED_NAME,
        "permissions": PERMISSIONS,
        "will_push": sorted(genesis_files()),
        "to": "refs/heads/main",
    }


def _commit(work: Path, runner: Runner) -> str:
    runner(["init", "--bare", "-q", str(work / "genesis.git")], work)
    bare = work / "genesis.git"
    env = {"GIT_INDEX_FILE": str(work / "genesis.index")}
    for name, body in sorted(genesis_files().items()):
        source = work / name
        source.write_text(body, encoding="utf-8")
        blob = runner(["hash-object", "-w", "--no-filters", str(source)], bare).strip()
        entry = ["update-index", "--add", "--cacheinfo", f"100644,{blob},{name}"]
        runner(entry, bare, env=env)
    tree = runner(["write-tree"], bare, env=env).strip()
    made = ["-c", "commit.gpgSign=false", "commit-tree", tree, "-m", "genesis"]
    who = {"NAME": "basicly tracker", "EMAIL": "tracker@writers.basicly.invalid"}
    identity = {
        f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER") for key, value in who.items()
    }
    return runner(made, bare, env=identity).strip()


def init(text: str, *, confirmed: bool, runner: Runner = git_runner.run) -> dict[str, object]:
    url, allow_file = vault_clone.vault_source(text)
    shown = guide(url)
    with tempfile.TemporaryDirectory(prefix="basicly-vault-init-") as folder:
        work = Path(folder)
        try:
            found = heads(url, allow_file, runner, work)
        except git_runner.GitRunnerError:
            return {
                **shown,
                "exit": FIX,
                "fix": f"git cannot read {url}; check the address and your git login",
            }
        if found:
            return {
                **shown,
                "exit": REFUSED,
                "refused": f"{url} already has commits; name an empty repository",
            }
        if not confirmed:
            return {**shown, "pushed": False, "next": f"vault-init --vault {url} --yes"}
        commit = _commit(work, runner)
        vault_push_guard.check(
            work / "genesis.git",
            f"refs/heads/main {commit} refs/heads/main {'0' * len(commit)}\n",
        )
        pushed = ["push", "--quiet", git_runner.END_OF_OPTIONS, url, f"{commit}:refs/heads/main"]
        runner(pushed, work / "genesis.git", allow_file=allow_file)
    return {**shown, "pushed": True, "genesis": commit}


def no_genesis(text: str, runner: Runner = git_runner.run) -> bool:
    try:
        url, allow_file = vault_clone.vault_source(text)
        with tempfile.TemporaryDirectory(prefix="basicly-vault-probe-") as folder:
            return not heads(url, allow_file, runner, Path(folder))
    except _PROBE_ERRORS:
        return False
