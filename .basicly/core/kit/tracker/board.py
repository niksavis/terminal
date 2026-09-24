from __future__ import annotations

import html
import importlib.util
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + file_name + " is missing from beside board.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


queries = _load("queries.py", "basicly_tracker_kit_queries")
shaping = _load("shaping.py", "basicly_tracker_kit_shaping")
templates = _load("templates.py", "basicly_tracker_kit_templates")
differential = queries.differential

EMPTY_LEDGER = "This ledger holds no record yet."

MAX_NODES = 24
NODE_W = 150
NODE_H = 34
GAP_X = 70
GAP_Y = 14
PAD = 20

STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem; font: 14px/1.5 ui-sans-serif, system-ui, sans-serif; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
h2 { font-size: 1rem; margin: 2rem 0 .5rem; text-transform: uppercase;
     letter-spacing: .08em; opacity: .7; }
p.note { margin: .25rem 0 0; opacity: .7; }
table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #8884;
         vertical-align: top; }
th { font-weight: 600; opacity: .7; font-size: .85rem; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
code { font: 12px/1.4 ui-monospace, monospace; }
ul.counts { list-style: none; display: flex; flex-wrap: wrap; gap: 1.5rem;
            padding: 0; margin: .5rem 0 0; }
ul.counts li { display: flex; flex-direction: column; }
ul.counts .n { font-size: 1.6rem; font-variant-numeric: tabular-nums; }
ul.counts .k { font-size: .8rem; opacity: .7; text-transform: uppercase;
               letter-spacing: .06em; }
.owed { opacity: .75; }
.none { opacity: .6; font-style: italic; }
svg { max-width: 100%; height: auto; border: 1px solid #8884; border-radius: 4px; }
svg text { font: 11px ui-monospace, monospace; fill: currentColor; }
svg rect { stroke: currentColor; opacity: .85; }
svg line { stroke: currentColor; opacity: .5; }
svg marker path { fill: currentColor; }
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _rows(headers: Sequence[str], rows: Iterable[Sequence[object]], numeric=()) -> str:
    body = []
    for row in rows:
        cells = "".join(
            f'<td class="num">{cell}</td>' if index in numeric else f"<td>{cell}</td>"
            for index, cell in enumerate(row)
        )
        body.append(f"<tr>{cells}</tr>")
    if not body:
        return '<p class="none">nothing here</p>'
    head = "".join(f"<th>{_e(name)}</th>" for name in headers)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _title(row: Mapping[str, object]) -> str:
    fields = row.get("fields")
    held = fields.get("title") if isinstance(fields, Mapping) else None
    return str(held or "")


def _owed_by_record(directory: Path | str) -> dict[str, tuple]:
    states = queries.folded(directory)
    closed_statuses = differential.DEFAULT_VOCABULARY.closed_statuses
    template = templates.load(directory)
    return {
        record: shaping.owed(
            dict(state.fields), closed=state.status in closed_statuses, template=template
        )
        for record, state in states.items()
        if not state.tombstoned
    }


def _owed_cell(missing: Sequence[str]) -> str:
    if not missing:
        return '<span class="none">shaped</span>'
    short = [name.replace("## ", "") for name in missing]
    return f'<span class="owed">owes {_e(", ".join(short))}</span>'


def _counts(stats: Mapping[str, object]) -> str:
    held = stats.get("by_status")
    by_status: Mapping[str, object] = held if isinstance(held, Mapping) else {}
    cells = [("records", stats.get("records", 0)), ("ready", stats.get("ready", 0))]
    cells += [("waiting on a dependency", stats.get("blocked", 0))]
    cells += [(f"status {name}", value) for name, value in sorted(by_status.items())]
    items = "".join(
        f'<li><span class="n">{_e(value)}</span><span class="k">{_e(name)}</span></li>'
        for name, value in cells
    )
    return f'<ul class="counts">{items}</ul>'


def _levels(nodes: Sequence[str], edges: Sequence[tuple]) -> dict[str, int]:
    blockers: dict[str, list] = {node: [] for node in nodes}
    for source, target in edges:
        if source in blockers and target in blockers:
            blockers[source].append(target)
    level = dict.fromkeys(nodes, 0)
    for _ in range(len(nodes)):
        moved = False
        for node in nodes:
            want = max((level[one] + 1 for one in blockers[node]), default=0)
            if want > level[node]:
                level[node] = want
                moved = True
        if not moved:
            break
    return level


def _graph(nodes: Sequence[str], edges: Sequence[tuple], titles: Mapping[str, str]) -> str:
    if not nodes:
        return '<p class="none">no dispatchable record has a dependency to draw</p>'
    level = _levels(nodes, edges)
    columns: dict[int, list] = {}
    for node in nodes:
        columns.setdefault(level[node], []).append(node)
    at = {}
    for depth, members in columns.items():
        for index, node in enumerate(sorted(members)):
            at[node] = (
                PAD + depth * (NODE_W + GAP_X),
                PAD + index * (NODE_H + GAP_Y),
            )
    width = PAD * 2 + (max(columns) + 1) * NODE_W + max(columns) * GAP_X
    height = PAD * 2 + max(len(m) for m in columns.values()) * (NODE_H + GAP_Y)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="dependency graph">',
        '<defs><marker id="a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" '
        'markerHeight="7" orient="auto"><path d="M0 0 L8 4 L0 8 z"/>'
        "</marker></defs>",
    ]
    for source, target in edges:
        if source not in at or target not in at:
            continue
        sx, sy = at[source]
        tx, ty = at[target]
        parts.append(
            f'<line x1="{tx + NODE_W}" y1="{ty + NODE_H // 2}" x2="{sx}" '
            f'y2="{sy + NODE_H // 2}" stroke-width="1" marker-end="url(#a)"/>'
        )
    for node in sorted(at):
        x, y = at[node]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="4" '
            f'fill="none"/>'
            f"<title>{_e(titles.get(node) or node)}</title>"
            f'<text x="{x + 8}" y="{y + 21}">{_e(node[:18])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _dispatchable(directory: Path | str):
    vocabulary = differential.DEFAULT_VOCABULARY
    views, _children = queries.views_and_children(directory)
    edges = []
    for record in sorted(views):
        view = views[record]
        if view.tombstoned or not differential.is_dispatchable(view.status, vocabulary):
            continue
        edges.extend(
            (record, edge.target)
            for edge in view.dependencies
            if edge.type in vocabulary.blocking_types
        )
    return _whole_components(edges)


def _whole_components(edges: Sequence[tuple]):

    touching: dict[str, set] = {}
    for source, target in edges:
        touching.setdefault(source, set()).add(target)
        touching.setdefault(target, set()).add(source)
    seen: set = set()
    components = []
    for node in sorted(touching):
        if node in seen:
            continue
        stack = [node]
        member: set = set()
        while stack:
            one = stack.pop()
            if one in member:
                continue
            member.add(one)
            stack.extend(touching.get(one, ()))
        seen |= member
        components.append(sorted(member))
    kept: list = []
    for component in sorted(components, key=lambda members: (-len(members), members[0])):
        if len(kept) + len(component) > MAX_NODES:
            continue
        kept.extend(component)
    held = set(kept)
    return sorted(held), [pair for pair in edges if pair[0] in held and pair[1] in held]


def _waits_on(directory: Path | str):
    vocabulary = differential.DEFAULT_VOCABULARY
    views, _children = queries.views_and_children(directory)
    rows = []
    for record in sorted(views):
        view = views[record]
        if view.tombstoned or not differential.is_dispatchable(view.status, vocabulary):
            continue
        waits = sorted(
            edge.target for edge in view.dependencies if edge.type in vocabulary.blocking_types
        )
        if waits:
            rows.append((record, waits))
    return rows


def _blocking_edge_count(directory: Path | str) -> int:
    vocabulary = differential.DEFAULT_VOCABULARY
    views, _children = queries.views_and_children(directory)
    return sum(
        1
        for view in views.values()
        if not view.tombstoned and differential.is_dispatchable(view.status, vocabulary)
        for edge in view.dependencies
        if edge.type in vocabulary.blocking_types
    )


def page(directory: Path | str) -> str:

    stats = queries.stats(directory)
    ready = queries.ready(directory)
    blocked = queries.blocked(directory)
    owed = _owed_by_record(directory)
    records = queries.query_records(directory)
    titles = {str(row["record"]): _title(row) for row in records}

    if not records:
        body = f'<p class="none">{EMPTY_LEDGER}</p>'
    else:
        nodes, edges = _dispatchable(directory)
        total_edges = _blocking_edge_count(directory)
        body = "".join((
            _counts(stats),
            "<h2>Ready</h2>",
            _rows(
                ("rank", "record", "title", "score", "shape"),
                [
                    (
                        row["rank"],
                        f"<code>{_e(row['record'])}</code>",
                        _e(row["title"]),
                        row["score"],
                        _owed_cell(owed.get(str(row["record"]), ())),
                    )
                    for row in ready["records"]
                ],
                numeric=(0, 3),
            ),
            "<h2>Blocked</h2>",
            _rows(
                ("record", "status", "held by"),
                [
                    (
                        f"<code>{_e(row['record'])}</code>",
                        _e(row["status"]),
                        ", ".join(
                            f"<code>{_e(one['record'])}</code> ({_e(one['status'])})"
                            for one in row["blocked_by"]
                        )
                        or '<span class="none">children</span>',
                    )
                    for row in blocked["records"]
                ],
            ),
            "<h2>Dependencies</h2>",
            _graph(nodes, edges, titles),
            f'<p class="note">{len(nodes)} of {stats["records"]} record(s) and '
            f"{len(edges)} of {total_edges} blocking edge(s) drawn. Only whole dependency "
            f"clusters are drawn, up to {MAX_NODES} records, so no edge on a drawn record "
            f"is cut: a record shown with no arrow into it really has nothing open "
            f"against it. An arrow points from what a record waits on to the record "
            f"itself.</p>",
            _rows(
                ("record", "waits on"),
                [
                    (
                        f"<code>{_e(record)}</code>",
                        ", ".join(f"<code>{_e(one)}</code>" for one in waits),
                    )
                    for record, waits in _waits_on(directory)
                ],
            ),
            '<p class="note">Every blocking edge the ledger holds between dispatchable '
            "records, whether or not the drawing above reaches it.</p>",
            "<h2>Every record</h2>",
            _rows(
                ("record", "status", "title", "shape"),
                [
                    (
                        f"<code>{_e(row['record'])}</code>",
                        _e(row.get("status") or ""),
                        _e(_title(row)),
                        _owed_cell(owed.get(str(row["record"]), ())),
                    )
                    for row in records
                ],
            ),
        ))
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Work tracker</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>Work tracker</h1>"
        f'<p class="note">Read from <code>{_e(Path(directory).as_posix())}</code>. '
        "Regenerate to refresh; nothing here updates on its own.</p>"
        f"{body}</body></html>\n"
    )


def write(directory: Path | str, out: Path | str) -> Path:

    target = Path(out)
    if str(target.parent) not in (".", ""):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page(directory), encoding="utf-8")
    return target
