from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_commit_msg_module():
    """Load the commit-msg hook module from its script path."""
    script_path = Path(__file__).resolve().parents[2] / ".scripts" / "git-hooks" / "commit-msg.py"
    spec = importlib.util.spec_from_file_location("commit_msg_hook", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_accepts_valid_conventional_message() -> None:
    """A valid conventional subject should pass validation."""
    module = _load_commit_msg_module()
    assert module.validate("chore(basicly): update generated manifest")


def test_validate_rejects_invalid_type_scope_and_trailing_punctuation() -> None:
    """A malformed type/scope and punctuation should fail validation."""
    module = _load_commit_msg_module()
    assert not module.validate("chote(word description): message;")


def test_validate_rejects_scope_with_spaces() -> None:
    """Scopes containing spaces should fail validation."""
    module = _load_commit_msg_module()
    assert not module.validate("chore(word description): message")


def test_validate_rejects_uppercase_description_start() -> None:
    """Descriptions that start uppercase should fail validation."""
    module = _load_commit_msg_module()
    assert not module.validate("chore(scope): Message")


def test_validate_rejects_too_short_description() -> None:
    """Descriptions shorter than the configured minimum should fail."""
    module = _load_commit_msg_module()
    assert not module.validate("fix: ab")


def test_validate_allows_merge_and_revert_subjects() -> None:
    """Merge and auto-generated revert subjects should be allowed."""
    module = _load_commit_msg_module()
    assert module.validate("Merge branch 'main' into feature")
    assert module.validate('Revert "bad commit"')
