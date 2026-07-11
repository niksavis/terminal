"""CLI for basicly."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .loader import load_fragments, load_targets
from .planner import plan_outputs
from .renderers.common import sha256_of_text
from .schema import PlannedOutput, ValidationError
from .skills import (
    check_synced_skills,
    discover_skills,
    resolve_skill_roots,
    sync_skills,
)

BASICLY_DIR = Path(".basicly")
FRAGMENTS_DIR = BASICLY_DIR / "fragments"
TARGETS_DIR = BASICLY_DIR / "targets"
TEMPLATES_DIR = BASICLY_DIR / "templates"
MANIFEST_PATH = BASICLY_DIR / "generated-manifest.json"


def _repo_root() -> Path:
    return Path.cwd()


def _format_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _load_context(repo_root: Path) -> tuple[list[Any], list[Any]]:
    targets = load_targets(repo_root / TARGETS_DIR)
    target_names = {t.name for t in targets}
    fragments = load_fragments(repo_root / FRAGMENTS_DIR, target_names)
    return fragments, targets


def _render_planned(repo_root: Path, planned: PlannedOutput) -> str:
    module_name = f"basicly.renderers.{planned.target_name}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"No renderer module for target '{planned.target_name}'") from exc
    return module.render(planned, repo_root / TEMPLATES_DIR, __version__)


def _write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _build_manifest(
    outputs: dict[Path, str],
    planned: list[PlannedOutput],
    existing_manifest: dict[str, Any] | None = None,
    partial: bool = False,
) -> dict[str, Any]:
    planned_by_path = {p.output_path: p for p in planned}
    existing_outputs: dict[str, Any] = {}
    if existing_manifest and isinstance(existing_manifest.get("outputs"), dict):
        existing_outputs = dict(existing_manifest["outputs"])

    new_outputs = {
        path.relative_to(_repo_root()).as_posix(): {
            "hash": sha256_of_text(content),
            "source_fragments": [f.id for f in planned_by_path[path].fragments],
        }
        for path, content in outputs.items()
    }

    merged_outputs = {**existing_outputs, **new_outputs} if partial else new_outputs

    return {
        "version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "outputs": merged_outputs,
    }


def cmd_list(_args: argparse.Namespace) -> int:
    """List active fragments in a table."""
    repo_root = _repo_root()
    fragments, _targets = _load_context(repo_root)
    active = [f for f in fragments if f.status == "active"]

    headers = f"{'id':<30} {'category':<15} {'priority':<10} "
    headers += f"{'applies_to':<20} {'scope':<20} {'status':<10}"
    print(headers)
    print("-" * 105)
    for f in sorted(active, key=lambda x: (x.category, -x.priority_value, x.id)):
        applies = ", ".join(f.applies_to)
        print(
            f"{f.id:<30} {f.category:<15} {f.priority:<10} "
            f"{applies:<20} {f.scope_summary:<20} {f.status:<10}"
        )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Build generated files for all or one target."""
    repo_root = _repo_root()
    fragments, targets = _load_context(repo_root)

    if args.target:
        target_names = {t.name for t in targets}
        if args.target not in target_names:
            print(
                f"Unknown target '{args.target}'. Known targets: {', '.join(sorted(target_names))}",
                file=sys.stderr,
            )
            return 1
        selected_targets = [t for t in targets if t.name == args.target]
        if not selected_targets or not selected_targets[0].enabled:
            print(f"Target '{args.target}' is disabled or unknown.", file=sys.stderr)
            return 1
        targets = selected_targets

    planned = plan_outputs(fragments, targets, repo_root)
    rendered: dict[Path, str] = {}
    changed_count = 0

    for item in planned:
        content = _render_planned(repo_root, item)
        rendered[item.output_path] = content
        changed = _write_if_changed(item.output_path, content)
        if changed:
            changed_count += 1
            print(f"Wrote {item.output_path.relative_to(repo_root)}")
        for target in targets:
            if (
                target.name == item.target_name
                and target.max_size_warning
                and len(content) > target.max_size_warning
            ):
                print(
                    f"Warning: {item.output_path.relative_to(repo_root)} "
                    f"exceeds {target.max_size_warning} characters "
                    f"({len(content)})",
                    file=sys.stderr,
                )

    manifest_path = repo_root / MANIFEST_PATH
    existing_manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_manifest = {}

    manifest = _build_manifest(rendered, planned, existing_manifest, bool(args.target))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {MANIFEST_PATH}")
    if changed_count == 0:
        print("No files changed.")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    """Check generated files and manifest are up to date."""
    repo_root = _repo_root()
    fragments, targets = _load_context(repo_root)
    planned = plan_outputs(fragments, targets, repo_root)

    mismatches: list[tuple[Path, str, str]] = []
    expected_manifest_outputs: dict[str, dict[str, Any]] = {}

    for item in planned:
        content = _render_planned(repo_root, item)
        rel_path = item.output_path.relative_to(repo_root).as_posix()
        expected_hash = sha256_of_text(content)
        expected_manifest_outputs[rel_path] = {
            "hash": expected_hash,
            "source_fragments": [f.id for f in item.fragments],
        }

        if not item.output_path.exists():
            mismatches.append((item.output_path, expected_hash, "missing"))
            continue

        actual = item.output_path.read_text(encoding="utf-8")
        actual_hash = sha256_of_text(actual)
        if actual_hash != expected_hash:
            mismatches.append((item.output_path, expected_hash, actual_hash))

    manifest_path = repo_root / MANIFEST_PATH
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Invalid manifest: {exc}", file=sys.stderr)
            return 1
    else:
        existing_manifest = {}

    if existing_manifest.get("outputs") != expected_manifest_outputs:
        mismatches.append((manifest_path, "manifest mismatch", "manifest mismatch"))

    if mismatches:
        print("Stale generated files detected. Run `basicly build` to fix.", file=sys.stderr)
        for path, expected, actual in mismatches:
            print(
                f"  {path.relative_to(repo_root)}: expected {expected}, found {actual}",
                file=sys.stderr,
            )
        return 1

    print("All generated files and manifest are up to date.")
    return 0


def _resolve_skill_output_roots(args: argparse.Namespace, repo_root: Path) -> list[Path]:
    roots_arg = getattr(args, "roots", None)
    use_default_roots = bool(getattr(args, "all_default_roots", False))
    return resolve_skill_roots(
        repo_root=repo_root,
        roots=roots_arg,
        use_default_roots=use_default_roots,
    )


def cmd_skills_list(_args: argparse.Namespace) -> int:
    """List skills available in the source collection."""
    repo_root = _repo_root()
    skills = discover_skills(repo_root)
    if not skills:
        print("No skills found in .basicly/skills")
        return 0

    print(f"{'slug':<24} {'name':<24} description")
    print("-" * 96)
    for skill in skills:
        print(f"{skill.slug:<24} {skill.name:<24} {skill.description}")
    return 0


def cmd_skills_build(args: argparse.Namespace) -> int:
    """Project skills from .basicly/skills into one or more destination roots."""
    repo_root = _repo_root()
    roots = _resolve_skill_output_roots(args, repo_root)
    result = sync_skills(repo_root, roots)

    for path in result.written:
        print(f"Wrote {_format_path(path, repo_root)}")

    if not result.written:
        print("No skill files changed.")

    print(
        "Skill projection complete: "
        f"{len(result.written)} written, {len(result.unchanged)} unchanged"
    )
    return 0


def cmd_skills_check(args: argparse.Namespace) -> int:
    """Check that projected skill roots are synchronized with source skills."""
    repo_root = _repo_root()
    roots = _resolve_skill_output_roots(args, repo_root)
    mismatches = check_synced_skills(repo_root, roots)

    if mismatches:
        print(
            "Stale skill projection detected. Run `basicly skills-build` to sync skill files.",
            file=sys.stderr,
        )
        for path, reason in mismatches:
            print(f"  {_format_path(path, repo_root)}: {reason}", file=sys.stderr)
        return 1

    print("Projected skills are up to date.")
    return 0


def _add_skill_root_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        help="Destination skills root. Repeat for multiple roots.",
    )
    parser.add_argument(
        "--all-default-roots",
        action="store_true",
        help="Use .claude/skills, .github/skills, and .agents/skills.",
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested command."""
    parser = argparse.ArgumentParser(prog="basicly")
    parser.add_argument("--version", action="version", version=f"basicly {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List active fragments")

    build_parser = subparsers.add_parser("build", help="Build generated files")
    build_parser.add_argument("--target", help="Build only the specified target")

    subparsers.add_parser("check", help="Check generated files are up to date")

    subparsers.add_parser("skills-list", help="List skills in .basicly/skills")

    skills_build_parser = subparsers.add_parser(
        "skills-build",
        help="Project skills from .basicly/skills",
    )
    _add_skill_root_args(skills_build_parser)

    skills_check_parser = subparsers.add_parser(
        "skills-check",
        help="Check projected skills are up to date",
    )
    _add_skill_root_args(skills_check_parser)

    args = parser.parse_args(argv)
    handlers = {
        "list": cmd_list,
        "build": cmd_build,
        "check": cmd_check,
        "skills-list": cmd_skills_list,
        "skills-build": cmd_skills_build,
        "skills-check": cmd_skills_check,
    }

    try:
        handler = handlers.get(args.command)
        if handler is None:
            return 0
        return handler(args)
    except ValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
