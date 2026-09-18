# module-size-waiver: cohesion: the kit's contract is that a foreign harness can copy this file

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAP_FILENAME = "model-map.json"
MODELS_DIRNAME = "models"
CORE_DIR = Path(".basicly") / "core"

TIER_KEY = "tier"
MODEL_KEY = "model"

MAP_PATH_ENV = "BASICLY_MODEL_MAP"
DEFAULT_TIER_ENV = "BASICLY_DEFAULT_TIER"

HOST_SURFACES: dict[str, tuple[str, str]] = {
    "claude": ("anthropic", "anthropic"),
    "codex": ("openai", "openai"),
    "copilot": ("github-copilot", "anthropic"),
}

HOST_MODEL_ALIASES: dict[str, dict[str, str]] = {
    "claude": {"low": "haiku", "medium": "sonnet", "high": "opus", "maximum": "fable"},
}

HOST_DEFINITION_PATHS: dict[str, tuple[str, ...]] = {
    "claude": (".claude/agents/{name}.md",),
    "copilot": (".github/agents/{name}.agent.md", ".claude/agents/{name}.md"),
}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_FENCE = "---"
_MAX_FRONTMATTER_LINES = 200
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")


@dataclass(frozen=True)
class Resolution:
    model: str | None = None
    alias: str | None = None
    tier: str | None = None
    surface: str | None = None
    vendor: str | None = None
    source: str | None = None
    reason: str | None = None
    skipped: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "alias": self.alias,
            "tier": self.tier,
            "surface": self.surface,
            "vendor": self.vendor,
            "source": self.source,
            "reason": self.reason,
            "skipped": [{"vendor": vendor, "reason": why} for vendor, why in self.skipped],
        }


@dataclass(frozen=True)
class TierResolver:
    mapping: dict
    default_tier: str | None = None
    map_path: Path | None = None

    @classmethod
    def from_map_path(cls, path: Path, *, default_tier: str | None = None) -> TierResolver | None:
        mapping = load_map(path)
        if mapping is None:
            return None
        return cls(mapping, default_tier=default_tier, map_path=path)

    @classmethod
    def discover(
        cls, root: Path | None = None, *, default_tier: str | None = None
    ) -> TierResolver | None:
        path = find_map(root)
        if path is None:
            return None
        return cls.from_map_path(path, default_tier=default_tier)

    @property
    def tier_order(self) -> tuple[str, ...]:

        order = self.mapping.get("tier_order")
        if not isinstance(order, list):
            return ()
        return tuple(str(tier) for tier in order)

    def model_for(self, tier: str, vendor: str, surface: str) -> str | None:

        return self._cell(tier, vendor, surface)[0]

    def resolve(
        self,
        host: str,
        *,
        definition: Path | None = None,
        tier: str | None = None,
        vendor: str | None = None,
    ) -> Resolution:

        surfacing = HOST_SURFACES.get(host)
        if surfacing is None:
            known = ", ".join(sorted(HOST_SURFACES))
            return Resolution(reason=f"unknown host {host!r}; known hosts: {known}")
        surface, default_vendor = surfacing
        chosen_vendor = vendor or default_vendor
        declared, source = self._tier_for(tier, definition)
        if declared is None:
            return Resolution(
                surface=surface,
                vendor=chosen_vendor,
                reason="no tier is declared for this spawn and no default tier is configured",
            )
        order = self.tier_order
        if order and declared not in order:
            return Resolution(
                tier=declared,
                surface=surface,
                vendor=chosen_vendor,
                source=source,
                reason=f"unknown tier {declared!r}; the map declares {', '.join(order)}",
            )
        model, landed, reason, skipped = self._walk(declared, surface, vendor, default_vendor)
        return Resolution(
            model=model,
            alias=HOST_MODEL_ALIASES.get(host, {}).get(declared) if model else None,
            tier=declared,
            surface=surface,
            vendor=landed,
            source=source,
            reason=reason,
            skipped=skipped,
        )

    def _tier_for(self, tier: str | None, definition: Path | None) -> tuple[str | None, str | None]:
        if tier and tier.strip():
            return tier.strip().lower(), "argument"
        if definition is not None:
            declared = declared_tier(definition)
            if declared:
                return declared, "definition"
        if self.default_tier and self.default_tier.strip():
            return self.default_tier.strip().lower(), "default"
        return None, None

    def _cell(self, tier: str, vendor: str, surface: str) -> tuple[str | None, str | None]:

        tiers = self.mapping.get("tiers")
        entry = tiers.get(tier) if isinstance(tiers, dict) else None
        vendors = entry.get("vendors") if isinstance(entry, dict) else None
        vendor_entry = vendors.get(vendor) if isinstance(vendors, dict) else None
        surfaces = vendor_entry.get("surfaces") if isinstance(vendor_entry, dict) else None
        cell = surfaces.get(surface) if isinstance(surfaces, dict) else None
        if not isinstance(cell, dict):
            return None, f"the model map carries no cell for {vendor} {tier} on {surface}"
        model = cell.get("model")
        if cell.get("status") != "available" or not isinstance(model, str) or not model:
            reason = cell.get("reason") or "the map marks this cell unavailable"
            return None, f"{vendor} {tier} is unavailable on {surface}: {reason}"
        return model, None

    def _vendor_order(self, tier: str) -> tuple[str, ...]:

        tiers = self.mapping.get("tiers")
        entry = tiers.get(tier) if isinstance(tiers, dict) else None
        order = entry.get("vendor_order") if isinstance(entry, dict) else None
        if not isinstance(order, list):
            return ()
        return tuple(str(vendor) for vendor in order if isinstance(vendor, str))

    def _walk(
        self, tier: str, surface: str, pinned: str | None, default_vendor: str
    ) -> tuple[str | None, str, str | None, tuple[tuple[str, str], ...]]:

        if pinned is not None:
            model, reason = self._cell(tier, pinned, surface)
            return model, pinned, reason, ()
        order = self._vendor_order(tier) or (default_vendor,)
        skipped: list[tuple[str, str]] = []
        for vendor in order:
            model, reason = self._cell(tier, vendor, surface)
            if model is not None:
                return model, vendor, None, tuple(skipped)
            skipped.append((vendor, reason or "no model"))
        tried = ", ".join(vendor for vendor, _ in skipped)
        return (
            None,
            order[-1],
            f"no vendor serves {tier} on {surface}; tried {tried}",
            tuple(skipped),
        )


def find_map(root: Path | None = None, *, beside_the_kit: bool = True) -> Path | None:

    start = Path(root) if root is not None else Path.cwd()
    for base in [start, *start.parents]:
        candidate = base / CORE_DIR / MODELS_DIRNAME / MAP_FILENAME
        if candidate.is_file():
            return candidate
    here = Path(__file__).resolve().parent
    vendored = here / MAP_FILENAME
    if here.is_relative_to(start.resolve()) and vendored.is_file():
        return vendored
    if not beside_the_kit:
        return None
    here = Path(__file__).resolve().parent
    for candidate in (here.parents[1] / MODELS_DIRNAME / MAP_FILENAME, here / MAP_FILENAME):
        if candidate.is_file():
            return candidate
    return None


def load_map(path: Path) -> dict | None:

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tiers"), dict):
        return None
    return parsed


def default_roots(root: Path | None = None) -> list[Path]:

    bases = [Path(root) if root is not None else Path.cwd()]
    try:
        home = Path.home()
    except RuntimeError:
        return bases
    if home not in bases:
        bases.append(home)
    return bases


def find_definition(name: str, host: str, roots: list[Path] | None = None) -> Path | None:

    if not _NAME_RE.match(name):
        return None
    bases = roots if roots is not None else default_roots()
    for base in bases:
        for template in HOST_DEFINITION_PATHS.get(host, ()):
            candidate = Path(base) / template.format(name=name)
            if candidate.is_file():
                return candidate
    return None


def declared_tier(path: Path) -> str | None:

    return declared_value(path, TIER_KEY)


def declared_value(path: Path, key: str) -> str | None:

    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return _frontmatter_value(handle, key)
    except OSError:
        return None


def _frontmatter_value(lines: Iterable[str], key: str) -> str | None:
    for index, line in enumerate(lines):
        text = line.rstrip("\n")
        if index == 0:
            if text.lstrip("\ufeff").strip() != _FENCE:
                return None
            continue
        if index > _MAX_FRONTMATTER_LINES or text.strip() == _FENCE:
            return None
        match = _KEY_RE.match(text)
        if match is not None and match.group(1) == key:
            return _scalar(match.group(2)) or None
    return None


def _scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip().lower()
    return value.split(" #", 1)[0].strip().lower()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a model tier to a concrete model for one host surface."
    )
    parser.add_argument("--host", required=True, choices=sorted(HOST_SURFACES))
    parser.add_argument("--name", help="subagent name to look a definition up by")
    parser.add_argument("--definition", help="path to the agent definition to read a tier from")
    parser.add_argument("--tier", help="tier to resolve, outranking the definition")
    parser.add_argument("--default-tier", help="tier for a definition that declares none")
    parser.add_argument("--vendor", help="override the host's default vendor")
    parser.add_argument("--map", help=f"path to {MAP_FILENAME}, overriding discovery")
    parser.add_argument("--root", help="directory to search from (default: cwd)")
    return parser.parse_args(argv)


def _resolver_for(args: argparse.Namespace, root: Path) -> TierResolver | None:
    default_tier = args.default_tier or os.environ.get(DEFAULT_TIER_ENV)
    explicit = args.map or os.environ.get(MAP_PATH_ENV)
    if explicit:
        return TierResolver.from_map_path(Path(explicit), default_tier=default_tier)
    return TierResolver.discover(root, default_tier=default_tier)


def main(argv: list[str] | None = None) -> int:

    args = _parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()
    resolver = _resolver_for(args, root)
    if resolver is None:
        empty = Resolution(reason=f"no usable {MAP_FILENAME} was found for this repository")
        print(json.dumps(empty.as_dict(), sort_keys=True))
        return 1
    definition = Path(args.definition) if args.definition else None
    if definition is None and args.name:
        definition = find_definition(args.name, args.host, roots=default_roots(root))
    resolution = resolver.resolve(
        args.host, definition=definition, tier=args.tier, vendor=args.vendor
    )
    print(json.dumps(resolution.as_dict(), sort_keys=True))
    return 0 if resolution.model else 1


if __name__ == "__main__":
    sys.exit(main())
