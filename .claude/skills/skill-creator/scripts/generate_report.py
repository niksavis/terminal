#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: system fonts, no web fonts, rows named.

import argparse
import html
import json
import sys
from pathlib import Path

_STYLE = """    <style>
        body {
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            background: #faf9f5;
            color: #141413;
        }
        h1 { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; color: #141413; }
        .explainer {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
            color: #b0aea5;
            font-size: 0.875rem;
            line-height: 1.6;
        }
        .summary {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
        }
        .summary p { margin: 5px 0; }
        .best { color: #788c5d; font-weight: bold; }
        .table-container {
            overflow-x: auto;
            width: 100%;
        }
        table {
            border-collapse: collapse;
            background: white;
            border: 1px solid #e8e6dc;
            border-radius: 6px;
            font-size: 12px;
            min-width: 100%;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border: 1px solid #e8e6dc;
            white-space: normal;
            word-wrap: break-word;
        }
        th {
            font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            background: #141413;
            color: #faf9f5;
            font-weight: 500;
        }
        th.test-col {
            background: #6a9bcc;
        }
        th.query-col { min-width: 200px; }
        td.description {
            font-family: monospace;
            font-size: 11px;
            word-wrap: break-word;
            max-width: 400px;
        }
        td.result {
            text-align: center;
            font-size: 16px;
            min-width: 40px;
        }
        td.test-result {
            background: #f0f6fc;
        }
        .pass { color: #788c5d; }
        .fail { color: #c44; }
        .rate {
            font-size: 9px;
            color: #b0aea5;
            display: block;
        }
        tr:hover { background: #faf9f5; }
        .score {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11px;
        }
        .score-good { background: #eef2e8; color: #788c5d; }
        .score-ok { background: #fef3c7; color: #d97706; }
        .score-bad { background: #fceaea; color: #c44; }
        .train-label { color: #b0aea5; font-size: 10px; }
        .test-label { color: #6a9bcc; font-size: 10px; font-weight: bold; }
        .best-row { background: #f5f8f2; }
        th.positive-col { border-bottom: 3px solid #788c5d; }
        th.negative-col { border-bottom: 3px solid #c44; }
        th.test-col.positive-col { border-bottom: 3px solid #788c5d; }
        th.test-col.negative-col { border-bottom: 3px solid #c44; }
        .legend {
            font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            display: flex; gap: 20px; margin-bottom: 10px; font-size: 13px; align-items: center;
        }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-swatch { width: 16px; height: 16px; border-radius: 3px; display: inline-block; }
        .swatch-positive { background: #141413; border-bottom: 3px solid #788c5d; }
        .swatch-negative { background: #141413; border-bottom: 3px solid #c44; }
        .swatch-test { background: #6a9bcc; }
        .swatch-train { background: #141413; }
    </style>
"""

_EXPLAINER = """    <div class="explainer">
        <strong>Optimizing the description of the skill.</strong> This page updates
        automatically as the loop tests different versions of the description. Each row is an
        iteration, a new description attempt. The columns show test queries: green checkmarks
        mean the skill triggered correctly (or correctly did not trigger), red crosses mean it
        got it wrong. The "Train" score shows performance on queries used to improve the
        description; the "Test" score shows performance on held-out queries the optimizer has
        not seen. When it is done, the best-performing description goes into skill.yaml.
    </div>
"""

_LEGEND = """
    <div class="legend">
        <span style="font-weight:600">Query columns:</span>
        <span class="legend-item"><span class="legend-swatch swatch-positive"></span>
            Should trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-negative"></span>
            Should not trigger</span>
        <span class="legend-item"><span class="legend-swatch swatch-train"></span> Train</span>
        <span class="legend-item"><span class="legend-swatch swatch-test"></span> Test</span>
    </div>
"""

_TABLE_HEAD = """
    <div class="table-container">
    <table>
        <thead>
            <tr>
                <th>Iter</th>
                <th>Train</th>
                <th>Test</th>
                <th class="query-col">Description</th>
"""


def query_columns(history: list[dict]) -> tuple[list[dict], list[dict]]:
    if not history:
        return [], []
    first = history[0]
    train = [
        {"query": r["query"], "should_trigger": r.get("should_trigger", True)}
        for r in first.get("train_results", first.get("results", []))
    ]
    test = [
        {"query": r["query"], "should_trigger": r.get("should_trigger", True)}
        for r in first.get("test_results") or []
    ]
    return train, test


def aggregate_runs(results: list[dict]) -> tuple[int, int]:
    correct = 0
    total = 0
    for r in results:
        runs = r.get("runs", 0)
        triggers = r.get("triggers", 0)
        total += runs
        correct += triggers if r.get("should_trigger", True) else runs - triggers
    return correct, total


def score_class(correct: int, total: int) -> str:
    if total > 0:
        ratio = correct / total
        if ratio >= 0.8:
            return "score-good"
        if ratio >= 0.5:
            return "score-ok"
    return "score-bad"


def _header_cell(qinfo: dict, extra: str) -> str:
    polarity = "positive-col" if qinfo["should_trigger"] else "negative-col"
    return f'                <th class="{extra}{polarity}">{html.escape(qinfo["query"])}</th>\n'


def _result_cell(result: dict, extra: str) -> str:
    did_pass = result.get("pass", False)
    icon = "✓" if did_pass else "✗"
    css_class = "pass" if did_pass else "fail"
    rate = f"{result.get('triggers', 0)}/{result.get('runs', 0)}"
    return (
        f'                <td class="result {extra}{css_class}">{icon}'
        f'<span class="rate">{rate}</span></td>\n'
    )


def iteration_row(
    h: dict, train_queries: list[dict], test_queries: list[dict], best_iter: object
) -> str:
    iteration = h.get("iteration", "?")
    train_results = h.get("train_results", h.get("results", []))
    test_results = h.get("test_results") or []
    train_by_query = {r["query"]: r for r in train_results}
    test_by_query = {r["query"]: r for r in test_results}

    train_correct, train_runs = aggregate_runs(train_results)
    test_correct, test_runs = aggregate_runs(test_results)
    train_class = score_class(train_correct, train_runs)
    test_class = score_class(test_correct, test_runs)
    row_class = "best-row" if iteration == best_iter else ""

    parts = [
        f"""            <tr class="{row_class}">
                <td>{iteration}</td>
                <td><span class="score {train_class}">{train_correct}/{train_runs}</span></td>
                <td><span class="score {test_class}">{test_correct}/{test_runs}</span></td>
                <td class="description">{html.escape(h.get("description", ""))}</td>
"""
    ]
    parts.extend(_result_cell(train_by_query.get(q["query"], {}), "") for q in train_queries)
    parts.extend(
        _result_cell(test_by_query.get(q["query"], {}), "test-result ") for q in test_queries
    )
    parts.append("            </tr>\n")
    return "".join(parts)


def generate_html(data: dict, auto_refresh: bool = False, skill_name: str = "") -> str:
    history = data.get("history", [])
    title_prefix = html.escape(skill_name + " \u2014 ") if skill_name else ""
    train_queries, test_queries = query_columns(history)
    refresh_tag = '    <meta http-equiv="refresh" content="5">\n' if auto_refresh else ""

    html_parts = [
        '<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="utf-8">\n'
        + refresh_tag
        + f"    <title>{title_prefix}Skill Description Optimization</title>\n"
        + _STYLE
        + f"</head>\n<body>\n    <h1>{title_prefix}Skill Description Optimization</h1>\n"
        + _EXPLAINER
    ]

    score_label = "(test)" if data.get("best_test_score") else "(train)"
    original = html.escape(data.get("original_description", "N/A"))
    best = html.escape(data.get("best_description", "N/A"))
    html_parts.append(f"""
    <div class="summary">
        <p><strong>Original:</strong> {original}</p>
        <p class="best"><strong>Best:</strong> {best}</p>
        <p><strong>Best Score:</strong> {data.get("best_score", "N/A")} {score_label}</p>
        <p><strong>Iterations:</strong> {data.get("iterations_run", 0)} |
           <strong>Train:</strong> {data.get("train_size", "?")} |
           <strong>Test:</strong> {data.get("test_size", "?")}</p>
    </div>
""")
    html_parts.append(_LEGEND)
    html_parts.append(_TABLE_HEAD)
    html_parts.extend(_header_cell(q, "") for q in train_queries)
    html_parts.extend(_header_cell(q, "test-col ") for q in test_queries)
    html_parts.append("            </tr>\n        </thead>\n        <tbody>\n")

    if test_queries:
        best_iter = max(history, key=lambda h: h.get("test_passed") or 0).get("iteration")
    else:
        best_iter = max(history, key=lambda h: h.get("train_passed", h.get("passed", 0))).get(
            "iteration"
        )

    html_parts.extend(iteration_row(h, train_queries, test_queries, best_iter) for h in history)
    html_parts.append("        </tbody>\n    </table>\n    </div>\n\n</body>\n</html>\n")

    return "".join(html_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML report from run_loop output")
    parser.add_argument("input", help="Path to JSON output from run_loop.py (or - for stdin)")
    parser.add_argument("-o", "--output", default=None, help="Output HTML file (default: stdout)")
    parser.add_argument("--skill-name", default="", help="Skill name to include in the title")
    args = parser.parse_args()

    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    html_output = generate_html(data, skill_name=args.skill_name)

    if args.output:
        Path(args.output).write_text(html_output, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(html_output)


if __name__ == "__main__":
    main()
