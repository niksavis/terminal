from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from terminal_setup.runner import Runner


def _enable_metrics(config: str) -> str:
    lines = config.splitlines(keepends=True)
    in_metrics = False
    for index, line in enumerate(lines):
        if line.startswith("["):
            in_metrics = line.strip() == "[git_metrics]"
        if in_metrics and re.match(r"disabled\s*=", line):
            lines[index] = "disabled = false\n"
            return "".join(lines)
    raise ValueError("config must explicitly set [git_metrics].disabled")


def check(config_path: Path) -> None:
    config_text = config_path.read_text(encoding="utf-8")
    config = tomllib.loads(config_text)
    modified_symbol = config["git_status"]["modified"]
    if not modified_symbol:
        raise ValueError("config must retain a modified-status symbol")
    runner = Runner(unattended=True)
    for executable in ("git", "starship"):
        if runner.which(executable) is None:
            raise RuntimeError(f"{executable} must be installed to run this check")

    with tempfile.TemporaryDirectory(prefix="terminal-prompt-check-") as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        calls = root / "filter-calls.txt"
        filter_script = root / "clean_filter.py"
        filter_script.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "with Path(sys.argv[1]).open('a', encoding='utf-8') as calls:\n"
            "    calls.write('clean\\n')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            STARSHIP_CACHE=str(root / "cache"),
            STARSHIP_SHELL="bash",
            TERM="xterm-256color",
        )
        runner.run(["git", "init", "--initial-branch=prompt-filter-check", str(repo)], env=env)
        filter_command = shlex.join([
            Path(sys.executable).as_posix(),
            filter_script.as_posix(),
            calls.as_posix(),
        ])
        for key, value in (
            ("user.name", "Prompt Check"),
            ("user.email", "prompt-check@example.invalid"),
            ("filter.prompt-check.clean", filter_command),
            ("filter.prompt-check.required", "true"),
        ):
            runner.run(["git", "config", "--local", key, value], cwd=repo, env=env)
        (repo / ".gitattributes").write_text("tracked.txt filter=prompt-check\n", encoding="utf-8")
        tracked = repo / "tracked.txt"
        tracked.write_text("original\n", encoding="utf-8")
        runner.run(["git", "add", "."], cwd=repo, env=env)
        runner.run(["git", "commit", "-m", "fixture"], cwd=repo, env=env)
        tracked.write_text("changed\nextra\n", encoding="utf-8")
        enabled = root / "metrics-enabled.toml"
        enabled.write_text(_enable_metrics(config_text), encoding="utf-8")
        configured = root / "configured.toml"
        configured.write_text(config_text, encoding="utf-8")

        results: list[tuple[int, float]] = []
        for candidate in (enabled, configured):
            calls.write_text("", encoding="utf-8")
            prompt_env = {**env, "STARSHIP_CONFIG": str(candidate)}
            start = time.monotonic()
            prompt = runner.run(["starship", "prompt"], cwd=repo, env=prompt_env)
            elapsed = time.monotonic() - start
            count = len(calls.read_text(encoding="utf-8").splitlines())
            if prompt.stderr.strip():
                raise RuntimeError(f"prompt emitted diagnostics: {prompt.stderr.strip()}")
            rendered = re.sub(r"\x1b\[[0-9;]*m", "", prompt.stdout)
            if "prompt-filter-check" not in rendered or modified_symbol not in rendered:
                raise RuntimeError("prompt must retain the branch and modified status")
            results.append((count, elapsed))

        control_calls, control_seconds = results[0]
        configured_calls, configured_seconds = results[1]
        if control_calls == 0:
            raise RuntimeError("positive control did not invoke the clean filter")
        if configured_calls != 0:
            raise RuntimeError(
                f"configured prompt invoked the clean filter {configured_calls} times"
            )
        print(
            f"PASS: enabled metrics filter calls={control_calls} ({control_seconds:.3f}s); "
            f"configured prompt filter calls={configured_calls} ({configured_seconds:.3f}s); "
            "branch and modified status retained"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check full prompts against a real Git clean filter"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "terminal_setup/templates/starship.toml",
    )
    args = parser.parse_args()
    check(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
