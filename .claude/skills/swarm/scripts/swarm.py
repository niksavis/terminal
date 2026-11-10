from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("important", "nit", "pre-existing")
JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
LOCATION = re.compile(r"[\w./-]+\.[A-Za-z0-9]+:\d+")
COMMAND = re.compile(r"(?:^|\s)\$ |\bran:", re.MULTILINE)
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CAP = 5
RISE = 1.0
CLEAN_ROUNDS = 2
LENS_RANGE = (3, 6)
PROPERTY_RANGE = (3, 9)
COUNCIL_SIZES = (3, 5)


@dataclass
class Report:
    lens: str
    status: str
    data: dict = field(default_factory=dict)
    problem: str = ""


def _names(raw: str, kind: str) -> list[str]:
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise SystemExit(f"swarm: name at least one {kind}, e.g. a,b,c")
    bad = [name for name in names if not NAME.match(name)]
    if bad:
        raise SystemExit(
            f"swarm: {kind} {bad[0]!r} must be lowercase letters, digits and hyphens, "
            "e.g. done-states"
        )
    if len(set(names)) != len(names):
        raise SystemExit(f"swarm: a {kind} is named twice; each gets one fresh agent")
    return names


def _findings_problem(findings: object) -> str:
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        return "findings is not a list of objects"
    if any(item.get("severity") not in SEVERITIES for item in findings):
        return f"severity must be one of {', '.join(SEVERITIES)}"
    return ""


def _shape_problem(data: object, lens: str, required: str) -> str:
    if not isinstance(data, dict):
        return "the json block is not an object"
    if data.get("lens") != lens:
        return f"the json block's lens is {data.get('lens')!r}, not {lens!r}"
    for field_name in dict.fromkeys((required, "findings")):
        if field_name not in data and not (field_name == "findings" and required == "vote"):
            return f"the json block has no {field_name!r} field"
    if data.get("verdict", "pass") not in ("pass", "fail"):
        return "verdict must be pass or fail"
    return _findings_problem(data.get("findings", []))


def unlisted_replies(directory: Path, names: list[str]) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("*.md") if path.stem not in names)


def refuse_unlisted(directory: Path, names: list[str], flag: str) -> None:
    extra = unlisted_replies(directory, names)
    if extra:
        raise SystemExit(
            f"swarm: {directory} holds {', '.join(extra)}, not named in {flag}; "
            f"add it to {flag}, or move it out of the folder and say so in the report"
        )


def lens_count_refusal(lenses: list[str]) -> str:
    low, high = LENS_RANGE
    if low <= len(lenses) <= high:
        return ""
    return f"use {low} to {high} lenses; add the closest lenses to reach {low}"


def read_report(directory: Path, lens: str, required: str = "verdict") -> Report:
    path = directory / f"{lens}.md"
    if not path.is_file():
        return Report(lens, "not run", problem=f"no {path.name}")
    blocks = JSON_BLOCK.findall(path.read_text(encoding="utf-8"))
    if not blocks:
        return Report(lens, "malformed", problem="no ```json block at the end")
    try:
        data = json.loads(blocks[-1])
    except json.JSONDecodeError as exc:
        return Report(lens, "malformed", problem=f"json error at line {exc.lineno}")
    problem = _shape_problem(data, lens, required)
    if problem:
        return Report(lens, "malformed", problem=problem)
    return Report(lens, "ok", data)


def cited(finding: dict) -> bool:
    evidence = str(finding.get("evidence", ""))
    return bool(LOCATION.search(evidence) or COMMAND.search(evidence))


def merge(reports: list[Report]) -> list[dict]:
    entries = [
        {
            **finding,
            "lens": report.lens,
            "cited": cited(finding),
            "places": set(LOCATION.findall(str(finding.get("evidence", "")))),
        }
        for report in reports
        for finding in report.data.get("findings", [])
    ]
    for entry in entries:
        entry["also"] = sorted({
            other["lens"]
            for other in entries
            if other["lens"] != entry["lens"] and other["places"] & entry["places"]
        })
    return sorted(
        entries, key=lambda item: (SEVERITIES.index(item["severity"]), -len(item["also"]))
    )


def cmd_check(args: argparse.Namespace) -> int:
    lenses = _names(args.lenses, "lens")
    refusal = lens_count_refusal(lenses)
    if refusal:
        raise SystemExit(f"swarm: {refusal}")
    refuse_unlisted(args.dir, lenses, "--lenses")
    reports = [read_report(args.dir, lens) for lens in lenses]
    print("| lens | status | verdict | important | nit | pre-existing | uncited |")
    print("|---|---|---|---|---|---|---|")
    for report in reports:
        findings = report.data.get("findings", [])
        counts = [sum(item["severity"] == level for item in findings) for level in SEVERITIES]
        uncited = sum(not cited(item) for item in findings)
        status = report.status if not report.problem else f"{report.status}: {report.problem}"
        verdict = str(report.data.get("verdict", "-"))
        print(
            f"| {report.lens} | {status} | {verdict} | {' | '.join(map(str, counts))} | {uncited} |"
        )
    print()
    for item in merge([report for report in reports if report.status == "ok"]):
        mark = "" if item["cited"] else " UNCITED"
        also = f" (also cited by {', '.join(item['also'])})" if item["also"] else ""
        print(f"- [{item['severity']}{mark}] {item['lens']}: {item.get('claim', '')}{also}")
        print(f"  evidence: {item.get('evidence', '')}")
        if item.get("fix"):
            print(f"  fix: {item['fix']}")
    missing = [report.lens for report in reports if report.status != "ok"]
    if missing:
        print(
            f"\nincomplete: {', '.join(missing)} not run or malformed; "
            "rerun once, then report them as not run"
        )
        return 1
    return 0


def _vote(report: Report, options: list[str]) -> tuple[str | None, str]:
    if report.status != "ok":
        return None, report.problem
    vote = report.data.get("vote")
    if not isinstance(vote, str) or not vote.strip():
        return None, "no vote field"
    if vote.strip() not in options:
        return None, f"vote {vote.strip()!r} is not one of {', '.join(options)}"
    return vote.strip(), ""


def cmd_tally(args: argparse.Namespace) -> int:
    voters = _names(args.voters, "voter")
    options = _names(args.options, "option")
    if len(voters) not in COUNCIL_SIZES:
        raise SystemExit(
            "council: use 3 voters, or 5 when the decision is hard to undo, "
            "so a tie cannot hide a majority"
        )
    if not 2 <= len(options) <= 4:
        raise SystemExit("council: give 2 to 4 options, e.g. --options per-event,shards")
    refuse_unlisted(args.dir, voters, "--voters")
    reports = [read_report(args.dir, voter, "vote") for voter in voters]
    votes = {report.lens: _vote(report, options) for report in reports}
    for report in reports:
        vote, problem = votes[report.lens]
        if vote is None:
            print(f"- {report.lens}: not run ({problem}); counts against every option")
        else:
            print(f"- {report.lens}: {vote}: {report.data.get('reason', '')}")
    counts = {
        option: [name for name, (vote, _) in votes.items() if vote == option] for option in options
    }
    print()
    for option, names in sorted(counts.items(), key=lambda item: -len(item[1])):
        print(f"{option}: {len(names)} of {len(voters)} ({', '.join(names) or 'none'})")
    winner = next(
        (option for option, names in counts.items() if len(names) * 2 > len(voters)), None
    )
    if winner is None:
        print("\ndecision: none; no option has a majority of all voters, so the user decides")
        return 2
    print(f"\ndecision: {winner}")
    for report in reports:
        vote, _ = votes[report.lens]
        if vote is None:
            print(f"dissent ({report.lens}): did not vote")
        elif vote != winner:
            print(f"dissent ({report.lens}, {vote}): {report.data.get('reason', '')}")
    return 0


def _load_state(path: Path) -> dict:
    start = "start a new climb with: climb-init --state NEW.json --properties a,b,c"
    if not path.is_file():
        raise SystemExit(f"hill-climb: no state at {path}; {start}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise SystemExit(f"hill-climb: {path} is not a climb state file; {start}") from None
    if not isinstance(state, dict) or not {"properties", "cap", "rounds"} <= set(state):
        raise SystemExit(f"hill-climb: {path} is not a climb state file; {start}")
    return state


def cmd_climb_init(args: argparse.Namespace) -> int:
    if args.state.exists():
        raise SystemExit(f"hill-climb: {args.state} exists; one state file per climb")
    properties = _names(args.properties, "property")
    low, high = PROPERTY_RANGE
    if not low <= len(properties) <= high:
        raise SystemExit(f"hill-climb: fix {low} to {high} properties in round 0")
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state = {"properties": properties, "cap": args.cap, "rounds": []}
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"climb started: {len(properties)} properties, cap {args.cap} rounds")
    return 0


def decide(state: dict) -> str:
    rounds = state["rounds"]
    if rounds and rounds[-1].get("past_stop"):
        return "stop: this round ran past the stop rule; run another only when the user asks"
    if len(rounds) >= CLEAN_ROUNDS and all(r["important"] == 0 for r in rounds[-CLEAN_ROUNDS:]):
        return f"stop: {CLEAN_ROUNDS} rounds in a row with no important finding"
    if len(rounds) >= 2:
        before, now = rounds[-2]["scores"], rounds[-1]["scores"]
        if not any(now[p] - before[p] >= RISE for p in state["properties"]):
            return f"stop: no property rose {RISE} since the last round"
    if len(rounds) >= state["cap"]:
        return f"stop: the cap of {state['cap']} rounds is reached"
    return "continue: revise the artifact, then grade it with at least one new lens"


def _grade(report: Report, prop: str) -> float | None:
    value = (
        report.data.get("grades", {}).get(prop)
        if isinstance(report.data.get("grades"), dict)
        else None
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
        return None
    return float(value)


def _round_refusal(state: dict, args: argparse.Namespace, lenses: list[str]) -> str:
    stopped = bool(state["rounds"]) and decide(state).startswith("stop")
    if stopped and not args.past_stop:
        return (
            f"the climb has stopped ({decide(state)}); "
            "add --past-stop only when the user asked for another round"
        )
    if args.past_stop and not stopped:
        return "--past-stop is only for a round after a stop; this climb has not stopped"
    if lens_count_refusal(lenses):
        return lens_count_refusal(lenses)
    if state["rounds"] and set(lenses) <= set(state["rounds"][-1]["lenses"]):
        return "use at least one lens not used in the last round"
    if str(args.dir.resolve()) in {r.get("dir") for r in state["rounds"]}:
        return f"{args.dir} is already recorded; put each round's replies in a new folder"
    return ""


def cmd_climb_round(args: argparse.Namespace) -> int:
    state = _load_state(args.state)
    lenses = _names(args.lenses, "lens")
    refusal = _round_refusal(state, args, lenses)
    if refusal:
        raise SystemExit(f"hill-climb: {refusal}")
    refuse_unlisted(args.dir, lenses, "--lenses")
    reports = [read_report(args.dir, lens, "grades") for lens in lenses]
    broken = [report for report in reports if report.status != "ok"]
    if broken:
        for report in broken:
            print(f"- {report.lens}: {report.status} ({report.problem})")
        left = len(lenses) - len(broken)
        advice = (
            "rerun those lenses once, or drop them from --lenses"
            if left >= LENS_RANGE[0]
            else f"rerun those lenses once; dropping them leaves {left}, below {LENS_RANGE[0]}"
        )
        print(f"round refused: {advice}")
        return 1
    grades: dict[str, list[float]] = {p: [] for p in state["properties"]}
    for report in reports:
        missing = [p for p in state["properties"] if _grade(report, p) is None]
        if missing:
            print(
                f"- {report.lens}: no 0-10 grade for {', '.join(missing)}; its other grades count"
            )
        for p in state["properties"]:
            value = _grade(report, p)
            if value is not None:
                grades[p].append(value)
    ungraded = [p for p, values in grades.items() if not values]
    if ungraded:
        print(f"round refused: no reviewer graded {', '.join(ungraded)}")
        return 1
    important = sum(item["severity"] == "important" for item in merge(reports))
    if not 0 <= args.refuted <= important:
        raise SystemExit(f"hill-climb: --refuted must be 0 to {important}, the important count")
    state["rounds"].append({
        "lenses": lenses,
        "dir": str(args.dir.resolve()),
        "refuted": args.refuted,
        "scores": {p: min(values) for p, values in grades.items()},
        "highs": {p: max(values) for p, values in grades.items()},
        "important": important - args.refuted,
        "past_stop": bool(args.past_stop),
    })
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    rounds = state["rounds"]
    print("| property | " + " | ".join(f"r{n}" for n in range(1, len(rounds) + 1)) + " |")
    print("|---|" + "---|" * len(rounds))
    for p in state["properties"]:
        cells = [
            f"{r['scores'][p]:g}"
            + (f"-{r['highs'][p]:g}" if r["highs"][p] != r["scores"][p] else "")
            for r in rounds
        ]
        print(f"| {p} | {' | '.join(cells)} |")
    print(f"| important findings | {' | '.join(str(r['important']) for r in rounds)} |")
    print(f"\ndecision: {decide(state)}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="swarm.py")
    sub = root.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="merge lens reports; a missing report is not run")
    check.add_argument("--lenses", required=True)
    check.add_argument("--dir", type=Path, required=True)
    check.set_defaults(run=cmd_check)
    tally = sub.add_parser("tally", help="count council votes; a majority of all voters decides")
    tally.add_argument("--voters", required=True)
    tally.add_argument("--options", required=True)
    tally.add_argument("--dir", type=Path, required=True)
    tally.set_defaults(run=cmd_tally)
    init = sub.add_parser("climb-init", help="start a hill climb with its fixed properties")
    init.add_argument("--state", type=Path, required=True)
    init.add_argument("--properties", required=True)
    init.add_argument("--cap", type=int, default=CAP, choices=range(1, 11))
    init.set_defaults(run=cmd_climb_init)
    step = sub.add_parser("climb-round", help="record one graded round and print the stop decision")
    step.add_argument("--state", type=Path, required=True)
    step.add_argument("--lenses", required=True)
    step.add_argument("--dir", type=Path, required=True)
    step.add_argument("--past-stop", action="store_true")
    step.add_argument("--refuted", type=int, default=0)
    step.set_defaults(run=cmd_climb_round)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
