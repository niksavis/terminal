"""Resolve a declared model tier to a concrete model with no basicly present.

The portable half of the tier vocabulary (basicly-wbsz.1). ``src/basicly/models.py``
does the same resolution *inside* the harness; this module does it for a spawn-path
hook and for a foreign harness, under one hard constraint: **no basicly**. No
``import basicly``, nothing on ``PATH``, no third-party package, no network, no
subprocess, no LLM. Two files are the whole dependency set — this module and
``model-map.json`` — so a consumer can copy both into an unrelated project and
drive their own spawner from them.

Three rules it exists to keep, the same three the in-harness resolver keeps:

- **An unavailable cell resolves to nothing; it never substitutes.** The map
  records ``"status": "unavailable"`` with no ``model`` key on purpose, so a
  lookup comes back empty instead of handing over some other tier's model. That
  silent demotion is what basicly-izda exists to prevent.
- **Surface is not cosmetic.** The same model is ``claude-haiku-4-5`` to
  Anthropic and ``claude-haiku-4.5`` to GitHub Copilot, and copilot rejects the
  hyphenated form outright, so the host being spawned picks the spelling.
- **A tier is read off the definition, never off basicly's catalog.** A consumer's
  own agent, written outside anything basicly ships, declares ``tier:`` in its
  frontmatter and resolves identically. That is the whole point of the tier being
  a portable vocabulary rather than an internal id.

The one deliberate difference from the in-harness resolver: **this one fails
closed and quiet where that one raises.** It runs in the spawn path, and on the
copilot host the hook is installed per machine rather than per repo (verified on
basicly-wbsz), so it is invoked in repositories that have no map at all.
Returning an empty :class:`Resolution` lets the caller leave the spawn untouched
so the host's own default applies; raising there would break every unrelated
repo on the machine. Empty is never silent, though: every :class:`Resolution`
without a ``model`` carries a ``reason`` saying which of the ways it came back
empty, and the CLI exits non-zero and prints that reason as JSON.

Written to stay usable on an interpreter older than this repo's floor — no syntax
newer than 3.9, since the consumer's python is not ours to choose. Only the repo
floor is exercised by tests, so treat that as care rather than as a guarantee. One
maintenance trap: this repo's ``ruff format`` targets 3.14 and rewrites a
parenthesized multi-exception ``except`` into the 3.14-only unparenthesized form,
so keep one exception class per handler here.

Invoke it from any language:

.. code-block:: sh

    python3 tier_resolver.py --host claude --name my-agent
    # {"alias": "opus", "model": "claude-opus-5", "source": "definition", ...}

``claude_tier_hook.py`` beside this module is the first consumer: a Claude Code
PreToolUse hook that pins a subagent spawn to its declared tier.

From python, put its directory on ``sys.path`` and import it by name. Loading it
by file path instead works too, but ``sys.modules`` must be populated *before*
the module body runs — ``dataclasses`` resolves a string annotation through
``sys.modules[cls.__module__]``, so the class definitions below fail without it:

.. code-block:: python

    spec = importlib.util.spec_from_file_location("tier_resolver", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tier_resolver"] = module   # required, not decoration
    spec.loader.exec_module(module)
"""

# module-size-waiver: cohesion: the kit's contract is that a foreign harness can copy this file
# and its hook flat into one directory and have them work, so splitting it along the
# seam the cap wants (the model-map lookup) would break the thing the module exists for.

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Where the map sits inside a catalog root, whichever root that is. Mirrors
# `basicly.models.MODELS_DIRNAME`/`MAP_FILENAME`; see the mirror note below.
MAP_FILENAME = "model-map.json"
MODELS_DIRNAME = "models"
CORE_DIR = Path(".basicly") / "core"

# The frontmatter keys an agent definition may declare. A definition that pins
# `model` itself has already answered the question a tier exists to answer, so a
# spawn hook reads that key to know when to stay out of the way.
TIER_KEY = "tier"
MODEL_KEY = "model"

# Read by `main` only. The library never touches the environment, so a caller's
# resolution depends on nothing but what it passed in — which is what makes a
# resolution reproducible from a run record rather than from a machine.
MAP_PATH_ENV = "BASICLY_MODEL_MAP"
DEFAULT_TIER_ENV = "BASICLY_DEFAULT_TIER"

# How each host spells a model, and whose models it serves by default.
#
# `surface` is the map surface whose spelling the host's model field accepts, and
# is a property of the host rather than a choice. `vendor` is the default only:
# the two single-vendor CLIs can serve nobody else, while copilot is a
# multi-vendor surface (its own store shows anthropic ids on 28 of 28 local
# sessions, which is why anthropic is its default) and is overridable per call.
#
# MIRROR, NOT A SECOND DEFINITION. This is `basicly.models.FAMILY_MODEL_SURFACES`
# copied, because the constraint above forbids importing it. It is a *checked*
# mirror, exactly like `.basicly/core/hooks/tracker-path-scan.py` mirrors
# `redact.MACHINE_PATH_RULES`: `tests/test_kit_resolver.py` asserts the two maps
# are equal AND that both halves resolve every (tier, host) cell to the same
# answer, so the copy cannot drift into a second, disagreeing rule. Edit both
# together.
HOST_SURFACES: dict[str, tuple[str, str]] = {
    "claude": ("anthropic", "anthropic"),
    "codex": ("openai", "openai"),
    "copilot": ("github-copilot", "anthropic"),
}

# What a host's *tool input* model field accepts, where that is narrower than the
# map surface spelling `HOST_SURFACES` picks. Same class of knowledge one notch
# in: a host can spell one model two ways on two different surfaces of its own.
#
# Claude is the case, measured on basicly-wbsz.2 against the 2.1.220 binary. Its
# Agent tool's `model` parameter is `enum(["sonnet","opus","haiku","fable"])`, so
# a full id is rejected there — while the *definition frontmatter* documents a
# full id as legal. One host, two vocabularies. A host absent from this table has
# no narrower surface, and a caller writes the model id.
#
# The table is committed data rather than a derivation off the map's `family`
# string, so that an upstream family rename cannot silently change an injected
# alias. `tests/test_kit_claude_hook.py` holds it to the map through
# `models.same_model`, the repo's own rule for whether a bare alias names an id —
# so the table cannot drift into pinning a tier to the wrong class of model.
HOST_MODEL_ALIASES: dict[str, dict[str, str]] = {
    "claude": {"low": "haiku", "medium": "sonnet", "high": "opus", "maximum": "fable"},
}

# Where each host reads a per-agent definition from, relative to a search root
# (verified against live host docs on basicly-a3yi). VS Code's copilot also reads
# the claude directory, which is why copilot lists both. A host absent from this
# table has no per-agent definition file at all — codex is the case today — so a
# tier for it can only come from an argument or the configured default.
HOST_DEFINITION_PATHS: dict[str, tuple[str, ...]] = {
    "claude": (".claude/agents/{name}.md",),
    "copilot": (".github/agents/{name}.agent.md", ".claude/agents/{name}.md"),
}

# A subagent name arrives from the host's tool input, i.e. from the model, and is
# interpolated into a path — so it is validated at that boundary rather than
# trusted. No separator and no leading dot means no traversal out of the roots.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_FENCE = "---"
# Frontmatter is at the top of the file by definition, so reading the whole of a
# long prompt to find a key that cannot be there is waste in the spawn path. The
# cap also bounds a file whose opening fence is never closed.
_MAX_FRONTMATTER_LINES = 200
# Top-level scalar keys only: anchored at column zero, so an indented key nested
# under some other mapping cannot be mistaken for the document's own `tier`.
# This is not a YAML parser and does not pretend to be one — PyYAML is a
# third-party import this module may not have. A value that is not a plain scalar
# simply fails to match a known tier and resolves to nothing.
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")


@dataclass(frozen=True)
class Resolution:
    """One tier resolution, including the ways it came back empty.

    ``model`` is the value to write into the host's model field, or ``None`` when
    nothing could be resolved — in which case ``reason`` says why, so a caller
    that leaves the spawn untouched can still log what it declined to do.
    """

    model: str | None = None
    # The same model in the host's narrower tool-input vocabulary, where it has
    # one (:data:`HOST_MODEL_ALIASES`). Never set without ``model``: an alias is
    # the alias *of a resolved model*, so a tier the map marks unavailable
    # resolves to neither rather than pinning by name what the map denies.
    alias: str | None = None
    tier: str | None = None
    surface: str | None = None
    vendor: str | None = None
    # Which input decided the tier: "argument", "definition", or "default".
    source: str | None = None
    # Why there is no model. ``None`` whenever there is one.
    reason: str | None = None
    # The vendors the walk passed over before ``vendor``, in the order it tried
    # them, with the reason each was skipped (D31). Empty when the first vendor
    # answered, when a vendor was pinned, or when the map carries no walk order.
    # Recorded because a resolution that silently landed on the third vendor and
    # one that landed on the first are indistinguishable from the model alone —
    # and the second is normal while the first means a vendor stopped serving a
    # tier, which is a thing an operator should get to see.
    skipped: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, object]:
        """The resolution as plain JSON-ready data, for a non-python caller."""
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
    """A loaded model map, ready to resolve tiers for a host.

    Construct it from :meth:`discover` (find the map the way a hook would) or
    :meth:`from_map_path` (a map the caller located itself); both return ``None``
    rather than raising when there is no usable map.
    """

    mapping: dict
    # The tier to use for a definition that declares none. ``None`` means an
    # undeclared tier resolves to nothing, which is the AC's fail-closed case.
    default_tier: str | None = None
    # Which file the mapping came from, for a caller that wants to log it.
    map_path: Path | None = None

    @classmethod
    def from_map_path(cls, path: Path, *, default_tier: str | None = None) -> TierResolver | None:
        """A resolver over the map at *path*, or ``None`` if it is not usable."""
        mapping = load_map(path)
        if mapping is None:
            return None
        return cls(mapping, default_tier=default_tier, map_path=path)

    @classmethod
    def discover(
        cls, root: Path | None = None, *, default_tier: str | None = None
    ) -> TierResolver | None:
        """A resolver over the map found from *root*, or ``None`` if there is none."""
        path = find_map(root)
        if path is None:
            return None
        return cls.from_map_path(path, default_tier=default_tier)

    @property
    def tier_order(self) -> tuple[str, ...]:
        """The map's own tier vocabulary, cheapest first.

        Taken from the map rather than hardcoded: the map publishes
        ``tier_order`` precisely so a consumer can walk the ladder without
        pinning the list, and reading it here means the kit carries no second
        copy of ``basicly.schema.MODEL_TIERS`` to keep in step.
        """
        order = self.mapping.get("tier_order")
        if not isinstance(order, list):
            return ()
        return tuple(str(tier) for tier in order)

    def model_for(self, tier: str, vendor: str, surface: str) -> str | None:
        """The model id for one map cell, or ``None`` when the cell has none.

        The primitive the README's plug-and-play example shows, with the raise
        turned into ``None``. Never another tier's model.
        """
        return self._cell(tier, vendor, surface)[0]

    def resolve(
        self,
        host: str,
        *,
        definition: Path | None = None,
        tier: str | None = None,
        vendor: str | None = None,
    ) -> Resolution:
        """Resolve the model to pin for a spawn on *host*.

        Args:
            host: A key of :data:`HOST_SURFACES`; decides the surface spelling.
            definition: The agent definition file to read a declared ``tier``
                from. Any markdown file with frontmatter, inside a basicly
                catalog or not.
            tier: An explicit tier that outranks the definition and the default.
            vendor: Overrides the host's default vendor.

        Returns:
            A :class:`Resolution`. ``model`` is ``None`` for an unknown host, an
            undeclared tier with no configured default, a tier the map does not
            carry, and a cell the map marks unavailable — each with its
            ``reason``, and never with a substituted model. ``alias`` carries the
            same model in *host*'s narrower tool-input vocabulary when it has one
            and a model resolved.
        """
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
        """The tier to resolve and which input decided it."""
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
        """One map cell as ``(model, reason)``; exactly one of the two is set.

        Every step is isinstance-guarded because a hand-edited or half-written
        map must resolve to nothing rather than raise in the spawn path. The
        ``collapse`` a three-class vendor's top tier carries needs no code here:
        the generator already resolved both tiers to the same model and
        cross-checks that they agree, which is why the collapse is data.
        """
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
        """The declared walk order for *tier*, or ``()`` when the map carries none.

        Empty for a map written before the order existed (schema 2), which is
        deliberate rather than an error: the kit is copied into repositories that
        may carry an older committed map, and a tolerant read there degrades to
        the single-vendor behaviour that map was written for. A map that *does*
        carry an order has already had it checked by the generator, which refuses
        anything but a permutation of the declared vendors.
        """
        tiers = self.mapping.get("tiers")
        entry = tiers.get(tier) if isinstance(tiers, dict) else None
        order = entry.get("vendor_order") if isinstance(entry, dict) else None
        if not isinstance(order, list):
            return ()
        return tuple(str(vendor) for vendor in order if isinstance(vendor, str))

    def _walk(
        self, tier: str, surface: str, pinned: str | None, default_vendor: str
    ) -> tuple[str | None, str, str | None, tuple[tuple[str, str], ...]]:
        """Find the first vendor serving *tier* on *surface* (D31).

        Returns ``(model, vendor, reason, skipped)``. A *pinned* vendor reads
        exactly one cell and never walks — an explicit request is answered or
        refused on its own terms, because silently serving a different vendor
        than the caller named is worse than saying no.

        The walk only ever moves sideways, across vendors at one tier. It cannot
        reach another tier, which is the property the map's per-cell refusal
        exists to protect: a spawn that asked for `maximum` gets `maximum` or
        gets nothing.
        """
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
    """Where to read the model map from, or ``None`` when there is none.

    The repository being worked in wins over the copy shipped beside this file,
    for the reason ``basicly.models.map_path`` gives: a repo that regenerated or
    reviewed its own map gets the one its own gates read, not the one that
    happened to be installed. Walking up from *root* is what lets a hook
    installed once per machine answer for whichever repo it is invoked in — and
    return ``None``, so the spawn is left alone, in a repo that has no map.

    Pass ``beside_the_kit=False`` to drop that last fallback and answer *only*
    for *root*'s own tree. A library wants the fallback — a copy of the two files
    dropped in a directory must still resolve. A machine-wide spawn hook must
    not have it: the kit is always beside itself, so the fallback would make the
    hook answer in every unrelated repository on the machine (measured on
    basicly-wbsz.2, where a directory with no map still resolved a model).
    """
    start = Path(root) if root is not None else Path.cwd()
    for base in [start, *start.parents]:
        candidate = base / CORE_DIR / MODELS_DIRNAME / MAP_FILENAME
        if candidate.is_file():
            return candidate
    if not beside_the_kit:
        return None
    here = Path(__file__).resolve().parent
    # Its own neighbours: the catalog's `models/`, two levels up from a
    # foldered kit, and a flat copy of the two files into one directory.
    for candidate in (here.parents[1] / MODELS_DIRNAME / MAP_FILENAME, here / MAP_FILENAME):
        if candidate.is_file():
            return candidate
    return None


def load_map(path: Path) -> dict | None:
    """The parsed model map at *path*, or ``None`` when it is not usable.

    Absent, unreadable, not JSON, and structurally wrong all come back ``None``:
    in the spawn path every one of them means the same thing, that this call
    cannot be answered and must be left to the host. The caller distinguishes
    them by the fact that it got ``None`` at all, and says so in its reason.
    """
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
    """Where to look for a definition: the project first, then the user's own.

    Matches where the hosts look for project-level and user-level agents, in that
    order. A home directory the platform cannot name is dropped rather than
    raised on: ``Path.home()`` raises when neither the environment nor the
    password database answers, which is a real state for a hook invoked from a
    service or a container, and a spawn-path resolver must miss rather than die.
    """
    bases = [Path(root) if root is not None else Path.cwd()]
    try:
        home = Path.home()
    except RuntimeError:
        return bases
    if home not in bases:
        bases.append(home)
    return bases


def find_definition(name: str, host: str, roots: list[Path] | None = None) -> Path | None:
    """The definition file for the subagent *name* on *host*, if one exists.

    *roots* defaults to :func:`default_roots`. A *name* that is not a bare agent
    slug is rejected outright rather than joined onto a path.
    """
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
    """The tier *path*'s frontmatter declares, or ``None`` when it declares none.

    Reads the file itself, so a consumer-authored definition that basicly has
    never seen resolves exactly like one basicly projected.
    """
    return declared_value(path, TIER_KEY)


def declared_value(path: Path, key: str) -> str | None:
    """One top-level frontmatter scalar of *path*, or ``None`` when it has none.

    The general form of :func:`declared_tier`, because a spawn hook needs a
    second key: a definition that already declares its own ``model`` must be left
    alone, and re-parsing frontmatter in the hook would be a second reader of the
    one rule this function is.

    Undecodable bytes are replaced rather than raised on: a definition whose
    prose is not valid UTF-8 still has a readable ASCII key line, and a crash
    here would take the spawn down with it.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return _frontmatter_value(handle, key)
    except OSError:
        return None


def _frontmatter_value(lines: Iterable[str], key: str) -> str | None:
    """Scan an open definition file's frontmatter block for one key."""
    for index, line in enumerate(lines):
        text = line.rstrip("\n")
        if index == 0:
            # A byte-order mark ahead of the opening fence is common in files an
            # editor on Windows wrote, and must not read as "no frontmatter".
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
    """A frontmatter scalar folded to a comparable tier token."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip().lower()
    return value.split(" #", 1)[0].strip().lower()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """The CLI surface: enough for a spawner in any language to drive this."""
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
    """Build the resolver the CLI arguments and environment ask for."""
    default_tier = args.default_tier or os.environ.get(DEFAULT_TIER_ENV)
    explicit = args.map or os.environ.get(MAP_PATH_ENV)
    if explicit:
        return TierResolver.from_map_path(Path(explicit), default_tier=default_tier)
    return TierResolver.discover(root, default_tier=default_tier)


def main(argv: list[str] | None = None) -> int:
    """Print one resolution as JSON; exit 0 when a model was resolved, else 1.

    The non-zero exit is the whole point of the fail-closed path being
    observable: a shell caller branches on the status without parsing anything,
    and the JSON on stdout still names the reason.
    """
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
