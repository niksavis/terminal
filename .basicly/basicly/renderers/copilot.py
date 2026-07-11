"""GitHub Copilot renderer."""

from __future__ import annotations

from .common import make_env, render_output


def render(planned, templates_dir, version):
    """Render a planned output for GitHub Copilot."""
    env = make_env(templates_dir)
    return render_output(env, planned, version)
