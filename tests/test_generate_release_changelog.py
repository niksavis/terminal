from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".scripts" / "generate_release_changelog.py"
_SPEC = importlib.util.spec_from_file_location("generate_release_changelog", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
generator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generator)


def test_a_section_leaves_a_blank_line_between_the_heading_and_the_list() -> None:
    section = generator._build_section("v1.2.0", "2026-09-25", "v1.1.0", ["feat: a (abc1234)"])

    heading = section.index("### Commit delta (auto-generated)")
    assert section[heading + 1] == ""
    assert section[heading + 2] == "- feat: a (abc1234)"


def test_a_section_without_commits_still_leaves_the_blank_line() -> None:
    section = generator._build_section("v1.2.0", "2026-09-25", None, [])

    heading = section.index("### Commit delta (auto-generated)")
    assert section[heading + 1 : heading + 3] == ["", "- No user-visible changes."]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _release_repo(tmp_path: Path, fragments: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "chore: start")
    _git(repo, "tag", "v0.1.0")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "feat: add a thing")
    folder = repo / "changelog.d"
    folder.mkdir()
    for name, body in fragments.items():
        (folder / name).write_text(body, encoding="utf-8")
    return repo


def _generate(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--tag", "v0.2.0", "--date", "2026-10-27"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_the_generator_folds_fragments_into_highlights_and_deletes_them(tmp_path: Path) -> None:
    repo = _release_repo(
        tmp_path,
        {"term-b2.fixed.md": "- Fix a bug.\n", "term-a1.added.md": "- Add a thing.\n"},
    )

    result = _generate(repo)

    assert result.returncode == 0, result.stderr
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Highlights\n\n- Add a thing.\n- Fix a bug.\n\n### Commit delta" in text
    assert list((repo / "changelog.d").iterdir()) == []
    assert "Folded 2 changelog fragments" in result.stdout


@pytest.mark.parametrize(
    ("name", "body", "reason"),
    [("notes.md", "- A note.\n", "is not named"), ("term-a1.added.md", "\n\n", "is empty")],
)
def test_the_generator_refuses_a_bad_fragment_and_writes_nothing(
    tmp_path: Path, name: str, body: str, reason: str
) -> None:
    repo = _release_repo(tmp_path, {name: body})

    result = _generate(repo)

    assert result.returncode == 2
    assert name in result.stderr
    assert reason in result.stderr
    assert not (repo / "CHANGELOG.md").exists()
    assert (repo / "changelog.d" / name).exists()


def test_a_second_run_keeps_the_highlights_of_the_section(tmp_path: Path) -> None:
    repo = _release_repo(tmp_path, {"term-a1.added.md": "- Add a thing.\n"})
    assert _generate(repo).returncode == 0

    result = _generate(repo)

    assert result.returncode == 0, result.stderr
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.count("### Highlights") == 1
    assert "### Highlights\n\n- Add a thing.\n\n### Commit delta" in text
