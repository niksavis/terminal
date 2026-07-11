"""Plan which fragments go into which output files."""

from __future__ import annotations

from pathlib import Path

from .schema import Fragment, OutputDef, PlannedOutput, Target


def plan_outputs(
    fragments: list[Fragment],
    targets: list[Target],
    repo_root: Path,
) -> list[PlannedOutput]:
    """Return the list of concrete output files to render."""
    active = [f for f in fragments if f.status == "active"]
    planned: list[PlannedOutput] = []

    for target in targets:
        if not target.enabled:
            continue
        for output in target.outputs:
            if output.path:
                selected = _select_fragments(active, output)
                if selected:
                    planned.append(
                        PlannedOutput(
                            target_name=target.name,
                            output_name=output.name,
                            output_path=repo_root / output.path,
                            template=output.template,
                            fragments=selected,
                        )
                    )
            elif output.path_template:
                scoped = _select_scoped_fragments(active, output)
                for fragment in scoped:
                    output_path = repo_root / output.path_template.format(fragment_id=fragment.id)
                    planned.append(
                        PlannedOutput(
                            target_name=target.name,
                            output_name=output.name,
                            output_path=output_path,
                            template=output.template,
                            fragments=[fragment],
                        )
                    )

    return planned


def _select_fragments(fragments: list[Fragment], output: OutputDef) -> list[Fragment]:
    selected = [
        f
        for f in fragments
        if _applies_to_matches(f.applies_to, output.applies_to_filter)
        and (not output.has_scope or f.is_scoped)
    ]
    return _sort_fragments(selected)


def _select_scoped_fragments(
    fragments: list[Fragment],
    output: OutputDef,
) -> list[Fragment]:
    selected = [
        f
        for f in fragments
        if f.is_scoped and _applies_to_matches(f.applies_to, output.applies_to_filter)
    ]
    return _sort_fragments(selected)


def _applies_to_matches(fragment_applies_to: list[str], filter_values: list[str]) -> bool:
    return any(target in filter_values for target in fragment_applies_to)


def _sort_fragments(fragments: list[Fragment]) -> list[Fragment]:
    return sorted(
        fragments,
        key=lambda f: (-f.priority_value, f.category, f.id),
    )
