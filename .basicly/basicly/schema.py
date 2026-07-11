"""Data classes and controlled vocabularies for fragments and targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PRIORITY_MAP = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

CATEGORIES = {
    "boundaries",
    "code-style",
    "commands",
    "decisions",
    "design",
    "hooks",
    "project",
    "security",
    "skills",
    "testing",
    "tools",
    "ci-cd",
}

STATUSES = {"active", "draft", "deprecated"}

DEFAULT_SCOPE = ["**"]


@dataclass(frozen=True)
class Fragment:
    """A single tool-agnostic policy/practice/decision."""

    id: str
    description: str
    category: str
    applies_to: list[str]
    priority: str = "medium"
    scope_paths: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPE))
    tags: list[str] = field(default_factory=list)
    status: str = "active"
    title: str | None = None
    body: str = ""
    source_path: Path | None = None
    # Phase 2 extension-mechanism fields (phase-1-safe defaults)
    source: str = "core"
    override: bool = False
    replaces: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Derive the title from the id if no title was provided."""
        object.__setattr__(self, "title", self.title or self._id_to_title(self.id))

    @staticmethod
    def _id_to_title(fragment_id: str) -> str:
        """Convert a kebab-case id to title case."""
        return " ".join(word.capitalize() for word in fragment_id.split("-"))

    @property
    def priority_value(self) -> int:
        """Return the numeric priority value for sorting."""
        return PRIORITY_MAP.get(self.priority, 2)

    @property
    def is_scoped(self) -> bool:
        """Return True if the fragment has a non-default scope."""
        return self.scope_paths != list(DEFAULT_SCOPE)

    @property
    def scope_summary(self) -> str:
        """Return a short scope representation for display."""
        if self.is_scoped:
            return self.scope_paths[0]
        return "**"


@dataclass(frozen=True)
class OutputDef:
    """Definition of a single generated output for a target."""

    name: str
    template: str
    path: str | None = None
    path_template: str | None = None
    applies_to_filter: list[str] = field(default_factory=list)
    has_scope: bool = False


@dataclass(frozen=True)
class Target:
    """A coding agent ecosystem with its own config format."""

    name: str
    enabled: bool
    tone: str
    max_size_warning: int
    outputs: list[OutputDef]


@dataclass(frozen=True)
class PlannedOutput:
    """A concrete output file planned for rendering."""

    target_name: str
    output_name: str
    output_path: Path
    template: str
    fragments: list[Fragment]


class ValidationError(Exception):
    """Raised when a fragment or target registry is invalid."""

    def __init__(self, message: str, path: Path | None = None) -> None:
        """Initialize with a message and optional source path."""
        super().__init__(message)
        self.message = message
        self.path = path

    def __str__(self) -> str:
        """Include the source path in the string when available."""
        if self.path:
            return f"{self.path}: {self.message}"
        return self.message
