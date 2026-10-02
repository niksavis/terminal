#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: run reading split into named steps.

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

_UNREADABLE = (json.JSONDecodeError, OSError)


def calculate_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}

    n = len(values)
    mean = sum(values) / n

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def eval_id_of(eval_dir: Path, eval_idx: int) -> int:
    metadata_path = eval_dir / "eval_metadata.json"
    if metadata_path.exists():
        try:
            return _read_json(metadata_path).get("eval_id", eval_idx)
        except _UNREADABLE:
            return eval_idx
    try:
        return int(eval_dir.name.split("-")[1])
    except ValueError:
        return eval_idx


def _timing(grading: dict, run_dir: Path) -> tuple[float, int]:
    seconds = grading.get("timing", {}).get("total_duration_seconds", 0.0)
    tokens = 0
    timing_file = run_dir / "timing.json"
    if seconds == 0.0 and timing_file.exists():
        try:
            timing_data = _read_json(timing_file)
        except json.JSONDecodeError:
            return seconds, tokens
        seconds = timing_data.get("total_duration_seconds", 0.0)
        tokens = timing_data.get("total_tokens", 0)
    return seconds, tokens


def read_run(run_dir: Path, eval_id: int) -> dict | None:
    grading_file = run_dir / "grading.json"
    if not grading_file.exists():
        print(f"Warning: grading.json not found in {run_dir}")
        return None
    try:
        grading = _read_json(grading_file)
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in {grading_file}: {e}")
        return None

    summary = grading.get("summary", {})
    seconds, tokens = _timing(grading, run_dir)
    metrics = grading.get("execution_metrics", {})

    raw_expectations = grading.get("expectations", [])
    for exp in raw_expectations:
        if "text" not in exp or "passed" not in exp:
            print(
                f"Warning: expectation in {grading_file} missing required fields "
                f"(text, passed, evidence): {exp}"
            )

    notes_summary = grading.get("user_notes_summary", {})
    return {
        "eval_id": eval_id,
        "run_number": int(run_dir.name.split("-")[1]),
        "pass_rate": summary.get("pass_rate", 0.0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "total": summary.get("total", 0),
        "time_seconds": seconds,
        "tokens": tokens or metrics.get("output_chars", 0),
        "tool_calls": metrics.get("total_tool_calls", 0),
        "errors": metrics.get("errors_encountered", 0),
        "expectations": raw_expectations,
        "notes": [
            *notes_summary.get("uncertainties", []),
            *notes_summary.get("needs_review", []),
            *notes_summary.get("workarounds", []),
        ],
    }


def load_run_results(benchmark_dir: Path) -> dict:
    runs_dir = benchmark_dir / "runs"
    if runs_dir.exists():
        search_dir = runs_dir
    elif list(benchmark_dir.glob("eval-*")):
        search_dir = benchmark_dir
    else:
        print(f"No eval directories found in {benchmark_dir} or {benchmark_dir / 'runs'}")
        return {}

    results: dict[str, list] = {}

    for eval_idx, eval_dir in enumerate(sorted(search_dir.glob("eval-*"))):
        eval_id = eval_id_of(eval_dir, eval_idx)
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir() or not list(config_dir.glob("run-*")):
                continue
            config_runs = results.setdefault(config_dir.name, [])
            for run_dir in sorted(config_dir.glob("run-*")):
                result = read_run(run_dir, eval_id)
                if result is not None:
                    config_runs.append(result)

    return results


def aggregate_results(results: dict) -> dict:
    run_summary = {}
    configs = list(results.keys())

    for config in configs:
        runs = results.get(config, [])

        if not runs:
            run_summary[config] = {
                "pass_rate": {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0},
                "time_seconds": {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0},
                "tokens": {"mean": 0, "stddev": 0, "min": 0, "max": 0},
            }
            continue

        run_summary[config] = {
            "pass_rate": calculate_stats([r["pass_rate"] for r in runs]),
            "time_seconds": calculate_stats([r["time_seconds"] for r in runs]),
            "tokens": calculate_stats([r.get("tokens", 0) for r in runs]),
        }

    primary = run_summary.get(configs[0], {}) if configs else {}
    baseline = run_summary.get(configs[1], {}) if len(configs) >= 2 else {}

    def delta(metric: str) -> float:
        return primary.get(metric, {}).get("mean", 0) - baseline.get(metric, {}).get("mean", 0)

    run_summary["delta"] = {
        "pass_rate": f"{delta('pass_rate'):+.2f}",
        "time_seconds": f"{delta('time_seconds'):+.1f}",
        "tokens": f"{delta('tokens'):+.0f}",
    }

    return run_summary


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "") -> dict:
    results = load_run_results(benchmark_dir)
    run_summary = aggregate_results(results)

    runs = [
        {
            "eval_id": result["eval_id"],
            "configuration": config,
            "run_number": result["run_number"],
            "result": {
                "pass_rate": result["pass_rate"],
                "passed": result["passed"],
                "failed": result["failed"],
                "total": result["total"],
                "time_seconds": result["time_seconds"],
                "tokens": result.get("tokens", 0),
                "tool_calls": result.get("tool_calls", 0),
                "errors": result.get("errors", 0),
            },
            "expectations": result["expectations"],
            "notes": result["notes"],
        }
        for config in results
        for result in results[config]
    ]

    eval_ids = sorted({r["eval_id"] for config in results.values() for r in config})

    return {
        "metadata": {
            "skill_name": skill_name or "<skill-name>",
            "skill_path": skill_path or "<path/to/skill>",
            "executor_model": "<model-name>",
            "analyzer_model": "<model-name>",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evals_run": eval_ids,
            "runs_per_configuration": 3,
        },
        "runs": runs,
        "run_summary": run_summary,
        "notes": [],
    }


def _spread(stats: dict, scale: float, places: int, unit: str = "") -> str:
    mean = stats.get("mean", 0) * scale
    stddev = stats.get("stddev", 0) * scale
    return f"{mean:.{places}f}{unit} ± {stddev:.{places}f}{unit}"


def generate_markdown(benchmark: dict) -> str:
    metadata = benchmark["metadata"]
    run_summary = benchmark["run_summary"]

    configs = [k for k in run_summary if k != "delta"]
    config_a = configs[0] if len(configs) >= 1 else "config_a"
    config_b = configs[1] if len(configs) >= 2 else "config_b"
    label_a = config_a.replace("_", " ").title()
    label_b = config_b.replace("_", " ").title()
    evals = ", ".join(map(str, metadata["evals_run"]))

    a_summary = run_summary.get(config_a, {})
    b_summary = run_summary.get(config_b, {})
    delta = run_summary.get("delta", {})

    def row(label: str, metric: str, scale: float, places: int, unit: str) -> str:
        a = _spread(a_summary.get(metric, {}), scale, places, unit)
        b = _spread(b_summary.get(metric, {}), scale, places, unit)
        change = delta.get(metric, "—")
        return f"| {label} | {a} | {b} | {change}{'' if unit == '%' else unit} |"

    lines = [
        f"# Skill Benchmark: {metadata['skill_name']}",
        "",
        f"**Model**: {metadata['executor_model']}",
        f"**Date**: {metadata['timestamp']}",
        f"**Evals**: {evals} ({metadata['runs_per_configuration']} runs each per configuration)",
        "",
        "## Summary",
        "",
        f"| Metric | {label_a} | {label_b} | Delta |",
        "| --- | --- | --- | --- |",
        row("Pass Rate", "pass_rate", 100, 0, "%"),
        row("Time", "time_seconds", 1, 1, "s"),
        row("Tokens", "tokens", 1, 0, ""),
    ]

    if benchmark.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in benchmark["notes"])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark run results into summary statistics"
    )
    parser.add_argument("benchmark_dir", type=Path, help="Path to the benchmark directory")
    parser.add_argument("--skill-name", default="", help="Name of the skill being benchmarked")
    parser.add_argument("--skill-path", default="", help="Path to the skill being benchmarked")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output path for benchmark.json (default: BENCHMARK_DIR/benchmark.json)",
    )

    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"Directory not found: {args.benchmark_dir}")
        sys.exit(1)

    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)

    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    output_md = output_json.with_suffix(".md")

    output_json.write_text(json.dumps(benchmark, indent=2), encoding="utf-8")
    print(f"Generated: {output_json}")

    output_md.write_text(generate_markdown(benchmark), encoding="utf-8")
    print(f"Generated: {output_md}")

    run_summary = benchmark["run_summary"]
    configs = [k for k in run_summary if k != "delta"]
    delta = run_summary.get("delta", {})

    print("\nSummary:")
    for config in configs:
        pr = run_summary[config]["pass_rate"]["mean"]
        label = config.replace("_", " ").title()
        print(f"  {label}: {pr * 100:.1f}% pass rate")
    print(f"  Delta:         {delta.get('pass_rate', '—')}")


if __name__ == "__main__":
    main()
