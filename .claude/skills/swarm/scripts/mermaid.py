from __future__ import annotations

from pathlib import Path

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


def _fence(lines: list[str]) -> str:
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
    for index, (_, vote) in enumerate(votes):
        if vote is not None and winner and vote != winner:
            lines.append(f"  v{index} -. dissent .-> d")
    return _fence(lines)


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
    return _fence(lines)
