#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: settings bundled, steps named, hash split.

import argparse
import hashlib
import json
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from generate_report import generate_html
from improve_description import DescriptionCase, improve_description
from run_eval import EvalSettings, add_eval_arguments, find_project_root, run_eval, settings_from
from skill_md import parse_skill_md


@dataclass(frozen=True)
class LoopPlan:
    max_iterations: int
    holdout: float
    verbose: bool
    live_report_path: Path | None
    log_dir: Path | None


def _shuffled(items: list[dict], seed: int) -> list[dict]:
    return sorted(items, key=lambda e: hashlib.sha256(f"{seed}:{e['query']}".encode()).hexdigest())


def split_eval_set(
    eval_set: list[dict], holdout: float, seed: int = 42
) -> tuple[list[dict], list[dict]]:
    trigger = _shuffled([e for e in eval_set if e["should_trigger"]], seed)
    no_trigger = _shuffled([e for e in eval_set if not e["should_trigger"]], seed)

    n_trigger_test = max(1, int(len(trigger) * holdout))
    n_no_trigger_test = max(1, int(len(no_trigger) * holdout))

    test_set = trigger[:n_trigger_test] + no_trigger[:n_no_trigger_test]
    train_set = trigger[n_trigger_test:] + no_trigger[n_no_trigger_test:]

    return train_set, test_set


def summarize(results: list[dict]) -> dict:
    passed = sum(1 for r in results if r["pass"])
    return {"passed": passed, "failed": len(results) - passed, "total": len(results)}


def history_entry(
    iteration: int, description: str, train_results: list[dict], test_results: list[dict] | None
) -> dict:
    train = summarize(train_results)
    test = summarize(test_results) if test_results is not None else None
    return {
        "iteration": iteration,
        "description": description,
        "train_passed": train["passed"],
        "train_failed": train["failed"],
        "train_total": train["total"],
        "train_results": train_results,
        "test_passed": test["passed"] if test else None,
        "test_failed": test["failed"] if test else None,
        "test_total": test["total"] if test else None,
        "test_results": test_results,
        "passed": train["passed"],
        "failed": train["failed"],
        "total": train["total"],
        "results": train_results,
    }


def print_eval_stats(label: str, results: list[dict], elapsed: float) -> None:
    pos = [r for r in results if r["should_trigger"]]
    neg = [r for r in results if not r["should_trigger"]]
    tp = sum(r["triggers"] for r in pos)
    fn = sum(r["runs"] for r in pos) - tp
    fp = sum(r["triggers"] for r in neg)
    tn = sum(r["runs"] for r in neg) - fp
    total = tp + tn + fp + fn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    accuracy = (tp + tn) / total if total > 0 else 0.0
    print(
        f"{label}: {tp + tn}/{total} correct, precision={precision:.0%} recall={recall:.0%} "
        f"accuracy={accuracy:.0%} ({elapsed:.1f}s)",
        file=sys.stderr,
    )
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        rate_str = f"{r['triggers']}/{r['runs']}"
        print(
            f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:60]}",
            file=sys.stderr,
        )


def best_iteration(history: list[dict], has_test: bool) -> tuple[dict, str]:
    if has_test:
        best = max(history, key=lambda h: h["test_passed"] or 0)
        return best, f"{best['test_passed']}/{best['test_total']}"
    best = max(history, key=lambda h: h["train_passed"])
    return best, f"{best['train_passed']}/{best['train_total']}"


def run_loop(
    eval_set: list[dict],
    skill_path: Path,
    description_override: str | None,
    settings: EvalSettings,
    plan: LoopPlan,
) -> dict:
    project_root = find_project_root()
    name, original_description, content = parse_skill_md(skill_path)
    current_description = description_override or original_description

    train_set, test_set = (
        split_eval_set(eval_set, plan.holdout) if plan.holdout > 0 else (eval_set, [])
    )
    if plan.verbose and test_set:
        print(
            f"Split: {len(train_set)} train, {len(test_set)} test (holdout={plan.holdout})",
            file=sys.stderr,
        )
    train_queries = {q["query"] for q in train_set}

    history: list[dict] = []
    exit_reason = "unknown"

    for iteration in range(1, plan.max_iterations + 1):
        if plan.verbose:
            rule = "=" * 60
            print(
                f"\n{rule}\nIteration {iteration}/{plan.max_iterations}\n"
                f"Description: {current_description}\n{rule}",
                file=sys.stderr,
            )

        t0 = time.monotonic()
        all_results = run_eval(
            train_set + test_set, name, current_description, project_root, settings
        )
        eval_elapsed = time.monotonic() - t0

        train_results = [r for r in all_results["results"] if r["query"] in train_queries]
        test_results = (
            [r for r in all_results["results"] if r["query"] not in train_queries]
            if test_set
            else None
        )
        entry = history_entry(iteration, current_description, train_results, test_results)
        history.append(entry)

        if plan.live_report_path:
            partial_output = {
                "original_description": original_description,
                "best_description": current_description,
                "best_score": "in progress",
                "iterations_run": len(history),
                "holdout": plan.holdout,
                "train_size": len(train_set),
                "test_size": len(test_set),
                "history": history,
            }
            plan.live_report_path.write_text(
                generate_html(partial_output, auto_refresh=True, skill_name=name),
                encoding="utf-8",
            )

        if plan.verbose:
            print_eval_stats("Train", train_results, eval_elapsed)
            if test_results is not None:
                print_eval_stats("Test ", test_results, 0)

        if entry["train_failed"] == 0:
            exit_reason = f"all_passed (iteration {iteration})"
            break

        if iteration == plan.max_iterations:
            exit_reason = f"max_iterations ({plan.max_iterations})"
            break

        if plan.verbose:
            print("\nImproving description...", file=sys.stderr)

        t0 = time.monotonic()
        blinded_history = [
            {k: v for k, v in h.items() if not k.startswith("test_")} for h in history
        ]
        case = DescriptionCase(
            name,
            content,
            current_description,
            {"results": train_results, "summary": summarize(train_results)},
            blinded_history,
        )
        current_description = improve_description(case, settings.model, plan.log_dir, iteration)

        if plan.verbose:
            improve_elapsed = time.monotonic() - t0
            print(f"Proposed ({improve_elapsed:.1f}s): {current_description}", file=sys.stderr)

    best, best_score = best_iteration(history, bool(test_set))

    if plan.verbose:
        print(f"\nExit reason: {exit_reason}", file=sys.stderr)
        print(f"Best score: {best_score} (iteration {best['iteration']})", file=sys.stderr)

    return {
        "exit_reason": exit_reason,
        "original_description": original_description,
        "best_description": best["description"],
        "best_score": best_score,
        "best_train_score": f"{best['train_passed']}/{best['train_total']}",
        "best_test_score": f"{best['test_passed']}/{best['test_total']}" if test_set else None,
        "final_description": current_description,
        "iterations_run": len(history),
        "holdout": plan.holdout,
        "train_size": len(train_set),
        "test_size": len(test_set),
        "history": history,
    }


def open_live_report(report: str, skill_path: Path) -> Path | None:
    if report == "none":
        return None
    if report == "auto":
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        live_report_path = (
            Path(tempfile.gettempdir())
            / f"skill_description_report_{skill_path.name}_{timestamp}.html"
        )
    else:
        live_report_path = Path(report)
    live_report_path.write_text(
        "<html><body><h1>Starting optimization loop...</h1>"
        "<meta http-equiv='refresh' content='5'></body></html>",
        encoding="utf-8",
    )
    webbrowser.open(live_report_path.resolve().as_uri())
    return live_report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval + improve loop")
    add_eval_arguments(parser)
    parser.add_argument("--max-iterations", type=int, default=5, help="Max improvement iterations")
    parser.add_argument(
        "--holdout",
        type=float,
        default=0.4,
        help="Fraction of eval set to hold out for testing (0 to disable)",
    )
    parser.add_argument("--model", required=True, help="Model for claude -p and the improvement")
    parser.add_argument(
        "--report",
        default="auto",
        help="Generate HTML report at this path ('auto' for a temp file, 'none' to disable)",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Save results.json, report.html and logs/ to a timestamped subdirectory here",
    )
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, _, _ = parse_skill_md(skill_path)
    live_report_path = open_live_report(args.report, skill_path)

    results_dir = None
    if args.results_dir:
        results_dir = Path(args.results_dir) / time.strftime("%Y-%m-%d_%H%M%S")
        results_dir.mkdir(parents=True, exist_ok=True)

    plan = LoopPlan(
        max_iterations=args.max_iterations,
        holdout=args.holdout,
        verbose=args.verbose,
        live_report_path=live_report_path,
        log_dir=results_dir / "logs" if results_dir else None,
    )
    output = run_loop(eval_set, skill_path, args.description, settings_from(args), plan)

    json_output = json.dumps(output, indent=2)
    print(json_output)
    report_html = generate_html(output, auto_refresh=False, skill_name=name)
    if live_report_path:
        live_report_path.write_text(report_html, encoding="utf-8")
        print(f"\nReport: {live_report_path}", file=sys.stderr)

    if results_dir:
        (results_dir / "results.json").write_text(json_output, encoding="utf-8")
        if live_report_path:
            (results_dir / "report.html").write_text(report_html, encoding="utf-8")
        print(f"Results saved to: {results_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
