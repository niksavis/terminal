"""A failing tool install must cost that tool, not the rest of the setup.

Installing a tool reaches the network and someone else's release assets, so it
fails for reasons unrelated to everything queued behind it. Before this, any such
failure reached the single top-level handler and ended the run.
"""

from __future__ import annotations

import subprocess

import pytest

from terminal_setup import prerequisites
from terminal_setup.runner import Runner


def boom() -> None:
    """Fail the way a download does: a non-zero command with stderr."""
    raise subprocess.CalledProcessError(
        returncode=22, cmd=["curl", "-fsSL", "https://example.invalid"], stderr="curl: (22) 404\n"
    )


def test_a_failing_step_does_not_propagate() -> None:
    """The exception must stop at the step, not reach the caller."""
    runner = Runner(dry_run=True)
    assert prerequisites.attempt(runner, "install thing", boom) is False


def test_a_failing_step_is_recorded_by_name() -> None:
    """A failure that is not raised must still be reported, or it is swallowed."""
    runner = Runner(dry_run=True)
    prerequisites.attempt(runner, "install thing", boom)
    assert runner.failures == ["install thing"]


def test_later_steps_still_run_after_a_failure() -> None:
    """The point of the change: what comes after a failed tool still happens."""
    runner = Runner(dry_run=True)
    ran: list[str] = []
    prerequisites.attempt(runner, "install thing", boom)
    prerequisites.attempt(runner, "deploy config", lambda: ran.append("deploy config"))
    assert ran == ["deploy config"]
    assert runner.failures == ["install thing"]


def test_a_successful_step_records_nothing() -> None:
    """The ledger drives the exit status, so a clean run must leave it empty."""
    runner = Runner(dry_run=True)
    assert prerequisites.attempt(runner, "install thing", lambda: None) is True
    assert runner.failures == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (subprocess.CalledProcessError(1, ["x"], stderr="last line\n"), "last line"),
        (subprocess.CalledProcessError(7, ["x"]), "exit code 7"),
        (RuntimeError("no package manager"), "no package manager"),
        (OSError(), "OSError"),
    ],
)
def test_the_reason_is_carried_into_the_report(error: Exception, expected: str) -> None:
    """A bare 'failed' is unactionable; the tool's own stderr is the useful part."""
    assert prerequisites._failure_reason(error) == expected


def test_an_unexpected_error_still_propagates() -> None:
    """Only the failure modes an install has are caught; a bug must not be hidden."""
    runner = Runner(dry_run=True)

    def bug() -> None:
        raise KeyError("a typo in our own dict")

    with pytest.raises(KeyError):
        prerequisites.attempt(runner, "install thing", bug)
