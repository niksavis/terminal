from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from .conftest import GUARD_EXIT, NETWORK_TOOLS


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows finds System32 programs before PATH for a bare executable name",
)
@pytest.mark.parametrize("tool", NETWORK_TOOLS)
def test_a_bare_network_tool_call_fails_at_once(tool: str) -> None:
    found = shutil.which(tool)
    assert found is not None
    result = subprocess.run([found, "--version"], check=False, capture_output=True, text=True)

    assert result.returncode == GUARD_EXIT
    assert f"test guard: {tool} is blocked in tests" in result.stderr
