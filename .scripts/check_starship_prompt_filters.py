from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from terminal_setup.runner import Runner


def check(config_path: Path) -> dict[str, float]:
    starship = shutil.which("starship")
    git = shutil.which("git")
    if starship is None or git is None:
        raise RuntimeError("This consumer check requires installed starship and git commands")
    source = config_path.read_text(encoding="utf-8")
    config = tomllib.loads(source)
    control, replacements = re.subn(
        r"(\[git_metrics\]\s*\ndisabled\s*=\s*)(?:true|false)", r"\1false", source
    )
    if replacements != 1:
        raise ValueError("Expected one explicit git_metrics disabled setting")
    timings: dict[str, float] = {}
    runner = Runner()
    with tempfile.TemporaryDirectory(prefix="starship-filter-check-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        marker = root / "filter-invocations"
        clean_filter = root / "clean-filter.py"
        clean_filter.write_text(
            "import pathlib,sys\n"
            f"with pathlib.Path({str(marker)!r}).open('a') as out: out.write('invoked\\n')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )

        def run_git(*args: str) -> None:
            runner.run([git, "-C", str(repo), *args], dry_run_safe=True)

        run_git("init", "-q", "--initial-branch=prompt-check")
        filter_command = shlex.join([Path(sys.executable).as_posix(), clean_filter.as_posix()])
        run_git("config", "filter.prompt-check.clean", filter_command)
        run_git("config", "filter.prompt-check.required", "true")
        (repo / ".gitattributes").write_text("tracked.txt filter=prompt-check\n", encoding="utf-8")
        (repo / "tracked.txt").write_text("base\n" * 50000, encoding="utf-8")
        run_git("add", ".gitattributes", "tracked.txt")
        run_git(
            "-c",
            "user.email=prompt-check@example.invalid",
            "-c",
            "user.name=Prompt Check",
            "commit",
            "-qm",
            "baseline",
        )
        (repo / "tracked.txt").write_text("changed\n" * 50000, encoding="utf-8")
        for name, text in (("positive_control", control), ("configured_prompt", source)):
            temporary_config = root / f"{name}.toml"
            temporary_config.write_text(text, encoding="utf-8")
            marker.write_text("", encoding="utf-8")
            environment = os.environ | {"STARSHIP_CONFIG": str(temporary_config), "PWD": str(repo)}
            started = time.monotonic()
            result = runner.run(
                [starship, "prompt"],
                cwd=repo,
                env=environment,
                dry_run_safe=True,
            )
            timings[name] = round(time.monotonic() - started, 3)
            calls = marker.read_text(encoding="utf-8").splitlines()
            if result.stderr:
                raise RuntimeError(f"{name} wrote to stderr: {result.stderr}")
            if name == "positive_control":
                if not calls:
                    raise AssertionError("Positive control did not exercise the clean filter")
            elif calls:
                raise AssertionError("Configured prompt still invokes the clean filter for metrics")
            plain_prompt = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
            if (
                "prompt-check" not in plain_prompt
                or config["git_status"]["modified"] not in plain_prompt
            ):
                raise AssertionError("Prompt lost its branch or modified indicator")
    return timings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "terminal_setup/templates/starship.toml",
    )
    args = parser.parse_args()
    timings = check(args.config)
    print(json.dumps({"result": "PASS", "filter_calls": 0, "seconds": timings}))


if __name__ == "__main__":
    main()
