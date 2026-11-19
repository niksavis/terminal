from __future__ import annotations

import subprocess

import pytest

from terminal_setup import prerequisites
from terminal_setup.runner import Runner


def boom() -> None:
    raise subprocess.CalledProcessError(
        returncode=22, cmd=["curl", "-fsSL", "https://example.invalid"], stderr="curl: (22) 404\n"
    )


def test_a_failing_step_does_not_propagate() -> None:
    runner = Runner(dry_run=True)
    assert prerequisites.attempt(runner, "install thing", boom) is False


def test_a_failing_step_is_recorded_by_name() -> None:
    runner = Runner(dry_run=True)
    prerequisites.attempt(runner, "install thing", boom)
    assert runner.failures == ["install thing"]


def test_later_steps_still_run_after_a_failure() -> None:
    runner = Runner(dry_run=True)
    ran: list[str] = []
    prerequisites.attempt(runner, "install thing", boom)
    prerequisites.attempt(runner, "deploy config", lambda: ran.append("deploy config"))
    assert ran == ["deploy config"]
    assert runner.failures == ["install thing"]


def test_a_successful_step_records_nothing() -> None:
    runner = Runner(dry_run=True)
    assert prerequisites.attempt(runner, "install thing", lambda: None) is True
    assert runner.failures == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (subprocess.CalledProcessError(1, ["x"], stderr="last line\n"), "last line"),
        (
            subprocess.CalledProcessError(
                2,
                ["x"],
                stderr="ok\ntar (child): xz: Cannot exec\n\ntar: Child returned status 2\n"
                "tar: Error is not recoverable\n",
            ),
            "tar (child): xz: Cannot exec | tar: Child returned status 2 | "
            "tar: Error is not recoverable",
        ),
        (subprocess.CalledProcessError(7, ["x"]), "exit code 7"),
        (RuntimeError("no package manager"), "no package manager"),
        (OSError(), "OSError"),
    ],
)
def test_the_reason_is_carried_into_the_report(error: Exception, expected: str) -> None:
    assert prerequisites._failure_reason(error) == expected


def test_an_unexpected_error_still_propagates() -> None:
    runner = Runner(dry_run=True)

    def bug() -> None:
        raise KeyError("a typo in our own dict")

    with pytest.raises(KeyError):
        prerequisites.attempt(runner, "install thing", bug)
