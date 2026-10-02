# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: renamed from utils.py, reads UTF-8.
from pathlib import Path

_BLOCK_INDICATORS = (">", "|", ">-", "|-")


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
    lines = content.split("\n")

    if lines[0].strip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")

    name = ""
    description = ""
    frontmatter_lines = lines[1:end_idx]
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if line.startswith("name:"):
            name = line[len("name:") :].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            value = line[len("description:") :].strip()
            if value in _BLOCK_INDICATORS:
                continuation_lines: list[str] = []
                i += 1
                while i < len(frontmatter_lines) and frontmatter_lines[i].startswith(("  ", "\t")):
                    continuation_lines.append(frontmatter_lines[i].strip())
                    i += 1
                description = " ".join(continuation_lines)
                continue
            description = value.strip('"').strip("'")
        i += 1

    return name, description, content
