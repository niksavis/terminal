#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: probe skill in .claude/skills, threads.

import argparse
import json
import os
import queue
import shutil
import subprocess  # nosec B404
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from skill_md import parse_skill_md

_PROBE_TOOLS = ("Skill", "Read")


@dataclass(frozen=True)
class EvalSettings:
    num_workers: int
    timeout: int
    runs_per_query: int
    trigger_threshold: float
    model: str | None


def find_project_root() -> Path:
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


def probe_prefix(skill_name: str) -> str:
    return f"{skill_name}-eval-"


def probe_skill_text(probe_name: str, description: str) -> str:
    indented_desc = "\n  ".join(description.split("\n"))
    return (
        f"---\n"
        f"name: {probe_name}\n"
        f"description: |\n"
        f"  {indented_desc}\n"
        f"---\n\n"
        f"# {probe_name}\n\n"
        f"This skill handles: {description}\n"
    )


def claude_command(query: str, model: str | None) -> list[str]:
    cmd = [
        "claude",
        "-p",
        query,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    if model:
        cmd.extend(["--model", model])
    return cmd


class TriggerWatch:
    def __init__(self, probe_name: str) -> None:
        self.probe_name = probe_name
        self.pending_tool: str | None = None
        self.accumulated = ""

    def feed(self, event: dict) -> bool | None:
        kind = event.get("type")
        if kind == "stream_event":
            return self._stream(event.get("event", {}))
        if kind == "assistant":
            return self._assistant(event.get("message", {}))
        if kind == "result":
            return False
        return None

    def _stream(self, stream_event: dict) -> bool | None:
        se_type = stream_event.get("type", "")
        if se_type == "content_block_start":
            return self._block_start(stream_event.get("content_block", {}))
        if se_type == "content_block_delta" and self.pending_tool:
            return self._block_delta(stream_event.get("delta", {}))
        if se_type in {"content_block_stop", "message_stop"}:
            if self.pending_tool:
                return self.probe_name in self.accumulated
            if se_type == "message_stop":
                return False
        return None

    def _block_start(self, block: dict) -> bool | None:
        if block.get("type") != "tool_use":
            return None
        if block.get("name", "") not in _PROBE_TOOLS:
            return False
        self.pending_tool = block.get("name", "")
        self.accumulated = ""
        return None

    def _block_delta(self, delta: dict) -> bool | None:
        if delta.get("type") == "input_json_delta":
            self.accumulated += delta.get("partial_json", "")
            if self.probe_name in self.accumulated:
                return True
        return None

    def _assistant(self, message: dict) -> bool | None:
        for item in message.get("content", []):
            if item.get("type") != "tool_use":
                continue
            tool_input = item.get("input", {})
            if item.get("name") == "Skill":
                return self.probe_name in tool_input.get("skill", "")
            if item.get("name") == "Read":
                return self.probe_name in tool_input.get("file_path", "")
            return False
        return None


def stream_events(process: subprocess.Popen[bytes], timeout: float) -> Iterator[dict]:
    lines: queue.Queue[bytes | None] = queue.Queue()
    stdout = process.stdout
    if stdout is None:
        raise ValueError("the claude process has no stdout pipe")

    def pump() -> None:
        for line in stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            return
        if line is None:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    project_root: Path,
    settings: EvalSettings,
) -> bool:
    probe_name = f"{probe_prefix(skill_name)}{uuid.uuid4().hex[:8]}"
    probe_dir = project_root / ".claude" / "skills" / probe_name
    probe_dir.mkdir(parents=True)
    try:
        (probe_dir / "SKILL.md").write_text(
            probe_skill_text(probe_name, skill_description), encoding="utf-8"
        )
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        process = subprocess.Popen(  # noqa: S603 # nosec B603 — argv list, no shell
            claude_command(query, settings.model),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=project_root,
            env=env,
        )
        try:
            watch = TriggerWatch(probe_prefix(skill_name))
            for event in stream_events(process, settings.timeout):
                verdict = watch.feed(event)
                if verdict is not None:
                    return verdict
            return False
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    finally:
        shutil.rmtree(probe_dir)


def _query_result(item: dict, triggers: list[bool], threshold: float) -> dict:
    trigger_rate = sum(triggers) / len(triggers)
    should_trigger = item["should_trigger"]
    did_pass = trigger_rate >= threshold if should_trigger else trigger_rate < threshold
    return {
        "query": item["query"],
        "should_trigger": should_trigger,
        "trigger_rate": trigger_rate,
        "triggers": sum(triggers),
        "runs": len(triggers),
        "pass": did_pass,
    }


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    project_root: Path,
    settings: EvalSettings,
) -> dict:
    query_triggers: dict[str, list[bool]] = {}
    query_items: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=settings.num_workers) as executor:
        future_to_item = {
            executor.submit(
                run_single_query, item["query"], skill_name, description, project_root, settings
            ): item
            for item in eval_set
            for _ in range(settings.runs_per_query)
        }
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            query_items[item["query"]] = item
            triggers = query_triggers.setdefault(item["query"], [])
            try:
                triggers.append(future.result())
            except (OSError, subprocess.SubprocessError, ValueError) as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                triggers.append(False)

    results = [
        _query_result(query_items[query], triggers, settings.trigger_threshold)
        for query, triggers in query_triggers.items()
    ]
    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def add_eval_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to the projected skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument(
        "--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold"
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")


def settings_from(args: argparse.Namespace) -> EvalSettings:
    return EvalSettings(
        num_workers=args.num_workers,
        timeout=args.timeout,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    add_eval_arguments(parser)
    parser.add_argument(
        "--model", default=None, help="Model for claude -p (default: the configured model)"
    )
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, _ = parse_skill_md(skill_path)
    description = args.description or original_description

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(eval_set, name, description, find_project_root(), settings_from(args))

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(
                f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}",
                file=sys.stderr,
            )

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
