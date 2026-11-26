from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from capability import drawn

LABEL_MAX = 80
QUESTION_FILE = "question.txt"


def label(text: str) -> str:
    flat = " ".join(str(text).split())
    if len(flat) > LABEL_MAX:
        flat = flat[: LABEL_MAX - 3] + "..."
    return flat.replace('"', "#quot;")


def question(directory: Path, default: str) -> str:
    path = directory / QUESTION_FILE
    if not path.is_file():
        return default
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[0].lstrip("# ") if lines else default


def fence(lines: list[str]) -> str:
    return "\n".join(["```mermaid", "flowchart TD", *lines, "```"])


def council_diagram(
    directory: Path,
    ballots: dict[str, tuple[str | None, str]],
    options: list[str],
    winner: str | None,
) -> str:
    votes = [(name, vote) for name, (vote, _) in ballots.items()]
    lines = [f'  q["{label(question(directory, "council"))}"]']
    for index, option in enumerate(options):
        count = sum(vote == option for _, vote in votes)
        lines.append(f'  o{index}["{label(option)}: {count} of {len(votes)}"]')
    if any(vote is None for _, vote in votes):
        lines.append('  nr["not run"]')
    for index, (voter, vote) in enumerate(votes):
        state = vote if vote is not None else "not run"
        lines.append(f'  q --> v{index}["{label(voter)}: {label(state)}"]')
        target = f"o{options.index(vote)}" if vote is not None else "nr"
        lines.append(f"  v{index} --> {target}")
    decision = f"decision: {winner}" if winner else "decision: none, the user decides"
    lines.append(f'  d["{label(decision)}"]')
    if winner:
        lines.append(f"  o{options.index(winner)} ==> d")
    else:
        lines.extend(f"  o{index} -. no majority .-> d" for index in range(len(options)))
    for index, (_, vote) in enumerate(votes):
        if vote is not None and winner and vote != winner:
            lines.append(f"  v{index} -. dissent .-> d")
    return fence(lines)


def lens_rows(reports: list) -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [
        (
            report.lens,
            str(report.data.get("verdict", "-")) if report.status == "ok" else "not run",
            [
                (item["severity"], str(item.get("claim", "")))
                for item in report.data.get("findings", [])
            ],
        )
        for report in reports
    ]


def swarm_diagram(directory: Path, reports: list, incomplete: bool) -> str:
    lenses = lens_rows(reports)
    lines = [f'  q["{label(question(directory, "swarm"))}"]']
    for index, (lens, state, findings) in enumerate(lenses):
        lines.append(f'  q --> l{index}["{label(lens)}: {label(state)}"]')
        for number, (severity, claim) in enumerate(findings):
            lines.append(f'  l{index} --> f{index}_{number}["{label(severity)}: {label(claim)}"]')
    result = "result: incomplete, a lens did not run" if incomplete else "result: every lens ran"
    lines.append(f'  r["{label(result)}"]')
    lines.extend(f"  l{index} --> r" for index in range(len(lenses)))
    return fence(lines)


def show(block: str) -> str:
    return block if drawn("flowchart") else ""


def print_shown(block: str) -> None:
    if shown := show(block):
        print(f"\n{shown}")


def plan_diagram(children: list[dict]) -> str:
    titles = [str(child.get("title", "")) for child in children]
    lines = [f'  c{index}["{label(title)}"]' for index, title in enumerate(titles)]
    for index, child in enumerate(children):
        for name in child.get("depends_on", []):
            if name not in titles:
                raise ValueError(f"depends_on names {name!r}, which is no child title")
            lines.append(f"  c{titles.index(name)} --> c{index}")
    return fence(lines)


def chain_diagram(links: list[str], control: str, tier: str) -> str:
    if not links:
        raise ValueError("the chain has no link; write one why per line")
    lines = [f'  w{index}["{label(link)}"]' for index, link in enumerate(links)]
    lines.extend(f"  w{index} --> w{index + 1}" for index in range(len(links) - 1))
    lines.append(f'  c["{label(f"control ({tier}): {control}")}"]')
    lines.append(f"  w{len(links) - 1} ==> c")
    return fence(lines)


def climb_diagram(state: dict, decision: str) -> str:
    lines = []
    for index, row in enumerate(state["rounds"]):
        low = min(row["scores"].values())
        text = f"round {index + 1}: lowest grade {low:g}, important {row['important']}"
        lines.append(f'  r{index}["{label(text)}"]')
        if index:
            lines.append(f"  r{index - 1} --> r{index}")
    lines.append(f'  d["{label(decision)}"]')
    lines.append(f"  r{len(state['rounds']) - 1} ==> d")
    return fence(lines)


def _plan(args: argparse.Namespace) -> str:
    with args.plan.open("rb") as handle:
        children = tomllib.load(handle).get("children", [])
    if not isinstance(children, list) or not children:
        raise ValueError(f"{args.plan} holds no [[children]] table")
    return plan_diagram(children)


def _chain(args: argparse.Namespace) -> str:
    text = args.links.read_text(encoding="utf-8")
    return chain_diagram(
        [line.strip() for line in text.splitlines() if line.strip()], args.control, args.tier
    )


def main(argv: list[str] | None = None) -> int:
    root = argparse.ArgumentParser(prog="mermaid.py")
    verbs = root.add_subparsers(dest="verb", required=True)
    plan = verbs.add_parser("plan", help="draw a decompose plan.toml")
    plan.add_argument("--plan", type=Path, required=True)
    chain = verbs.add_parser("chain", help="draw a root-cause chain, one why per line")
    chain.add_argument("--links", type=Path, required=True)
    chain.add_argument("--control", required=True)
    chain.add_argument("--tier", choices=("control", "warning", "documentation"), required=True)
    args = root.parse_args(argv)
    try:
        block = _plan(args) if args.verb == "plan" else _chain(args)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"mermaid.py {args.verb}: {error}", file=sys.stderr)
        return 2
    if shown := show(block):
        print(shown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
