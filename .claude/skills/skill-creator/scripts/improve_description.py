#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: basicly description rules, calm prompt.

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from skill_md import parse_skill_md

DESCRIPTION_LIMIT = 1024

_TAGGED = re.compile(r"<new_description>(.*?)</new_description>", re.DOTALL)

_GUIDANCE = f"""Based on the failures, write a new and improved description that is more likely
to trigger correctly. Do not overfit to the specific cases shown. Do not produce an
ever-expanding list of specific queries that this skill should or should not trigger for.
Generalize from the failures to broader categories of user intent and situations where this
skill would be useful or not useful, for two reasons:

1. Avoid overfitting.
2. The description is injected into every query next to many other skills, so each
   description must stay short.

Keep the description to about 100-200 words, even if that costs accuracy. The hard limit is
{DESCRIPTION_LIMIT} characters, so stay comfortably under it.

Rules of the catalog that will hold this description:
- Write it in the third person: say what the skill does, then "Use when a task ...".
  Never use the words you, your, I, we or our; the catalog lint refuses them.
- Put no angle-bracket tags in it; write a placeholder in capitals, e.g. tool-NAME.
- Focus on the intent of the user, what they are trying to achieve, not on how the skill
  works.
- The description competes with other skills for attention, so make it distinctive. Use
  the vocabulary that only this skill should answer to.
- If many attempts keep failing, change the sentence structure or the wording.

Mix up the style between iterations; the highest-scoring description is kept at the end.

Respond with only the new description text in <new_description> tags, nothing else."""


@dataclass(frozen=True)
class DescriptionCase:
    skill_name: str
    skill_content: str
    current_description: str
    eval_results: dict
    history: list[dict]


def _call_claude(prompt: str, model: str | None, timeout: int = 300) -> str:
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(  # noqa: S603 # nosec B603 — argv list, prompt on stdin
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p exited {result.returncode}\nstderr: {result.stderr}")
    return result.stdout


def _failure_lines(title: str, failures: list[dict]) -> str:
    if not failures:
        return ""
    lines = [f"{title}:"]
    lines.extend(
        f'  - "{r["query"]}" (triggered {r["triggers"]}/{r["runs"]} times)' for r in failures
    )
    return "\n".join(lines) + "\n\n"


def _attempt_block(h: dict) -> str:
    train_s = (
        f"{h.get('train_passed', h.get('passed', 0))}/{h.get('train_total', h.get('total', 0))}"
    )
    test_s = (
        f"{h.get('test_passed', '?')}/{h.get('test_total', '?')}"
        if h.get("test_passed") is not None
        else None
    )
    score_str = f"train={train_s}" + (f", test={test_s}" if test_s else "")
    block = f"<attempt {score_str}>\n"
    block += f'Description: "{h["description"]}"\n'
    if "results" in h:
        block += "Train results:\n"
        for r in h["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            block += f'  [{status}] "{r["query"][:80]}" (triggered {r["triggers"]}/{r["runs"]})\n'
    if h.get("note"):
        block += f"Note: {h['note']}\n"
    return block + "</attempt>\n\n"


def build_prompt(case: DescriptionCase) -> str:
    results = case.eval_results["results"]
    failed_triggers = [r for r in results if r["should_trigger"] and not r["pass"]]
    false_triggers = [r for r in results if not r["should_trigger"] and not r["pass"]]
    summary = case.eval_results["summary"]

    prompt = f"""You are optimizing a skill description for a Claude Code skill called
"{case.skill_name}". A skill is like a prompt with progressive disclosure: the agent sees a
title and a description when it decides whether to use the skill, and if it uses the skill,
it reads the .md file, which has more detail and can link to helper files, scripts and
further documentation in the skill folder.

The description appears in the "available_skills" list. When a user sends a query, the agent
decides whether to invoke the skill based only on the title and this description. The goal
is a description that triggers for relevant queries and does not trigger for irrelevant ones.

Here's the current description:
<current_description>
"{case.current_description}"
</current_description>

Current scores (Train: {summary["passed"]}/{summary["total"]}):
<scores_summary>
"""
    prompt += _failure_lines(
        "FAILED TO TRIGGER (should have triggered but did not)", failed_triggers
    )
    prompt += _failure_lines("FALSE TRIGGERS (triggered but should not have)", false_triggers)

    if case.history:
        prompt += (
            "Previous attempts (do not repeat these; try something structurally different):\n\n"
        )
        prompt += "".join(_attempt_block(h) for h in case.history)

    return (
        prompt
        + f"""</scores_summary>

Skill content (for context on what the skill does):
<skill_content>
{case.skill_content}
</skill_content>

"""
        + _GUIDANCE
    )


def _parse_description(text: str) -> str:
    match = _TAGGED.search(text)
    return match.group(1).strip().strip('"') if match else text.strip().strip('"')


def improve_description(
    case: DescriptionCase,
    model: str | None,
    log_dir: Path | None = None,
    iteration: int | None = None,
) -> str:
    prompt = build_prompt(case)
    text = _call_claude(prompt, model)
    description = _parse_description(text)

    transcript: dict = {
        "iteration": iteration,
        "prompt": prompt,
        "response": text,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > DESCRIPTION_LIMIT,
    }

    if len(description) > DESCRIPTION_LIMIT:
        shorten_prompt = (
            f"{prompt}\n\n"
            f"---\n\n"
            f"A previous attempt produced this description, which at "
            f"{len(description)} characters is over the {DESCRIPTION_LIMIT}-character hard "
            f'limit:\n\n"{description}"\n\n'
            f"Rewrite it to be under {DESCRIPTION_LIMIT} characters while keeping the most "
            f"important trigger words and intent coverage. Respond with only "
            f"the new description in <new_description> tags."
        )
        shorten_text = _call_claude(shorten_prompt, model)
        shortened = _parse_description(shorten_text)

        transcript["rewrite_prompt"] = shorten_prompt
        transcript["rewrite_response"] = shorten_text
        transcript["rewrite_description"] = shortened
        transcript["rewrite_char_count"] = len(shortened)
        description = shortened

    transcript["final_description"] = description

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"improve_iter_{iteration or 'unknown'}.json"
        log_file.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    return description


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Improve a skill description based on eval results"
    )
    parser.add_argument(
        "--eval-results", required=True, help="Path to eval results JSON (from run_eval.py)"
    )
    parser.add_argument("--skill-path", required=True, help="Path to the projected skill directory")
    parser.add_argument("--history", default=None, help="Path to history JSON (previous attempts)")
    parser.add_argument("--model", required=True, help="Model for improvement")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text(encoding="utf-8"))
    history = []
    if args.history:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))

    name, _, content = parse_skill_md(skill_path)
    current_description = eval_results["description"]
    summary = eval_results["summary"]

    if args.verbose:
        print(f"Current: {current_description}", file=sys.stderr)
        print(f"Score: {summary['passed']}/{summary['total']}", file=sys.stderr)

    case = DescriptionCase(name, content, current_description, eval_results, history)
    new_description = improve_description(case, args.model)

    if args.verbose:
        print(f"Improved: {new_description}", file=sys.stderr)

    output = {
        "description": new_description,
        "history": [
            *history,
            {
                "description": current_description,
                "passed": summary["passed"],
                "failed": summary["failed"],
                "total": summary["total"],
                "results": eval_results["results"],
            },
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
