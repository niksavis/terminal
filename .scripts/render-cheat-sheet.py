#!/usr/bin/env python3
"""Render terminal-cheat-sheet.md to a self-contained HTML page."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MD = REPO_ROOT / "terminal-cheat-sheet.md"
DEFAULT_HTML = REPO_ROOT / "terminal-cheat-sheet.html"


def _bi(name: str, path: str) -> str:
    """Return a Bootstrap Icons inline SVG."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        f'fill="currentColor" class="bi bi-{name}" viewBox="0 0 16 16" '
        f'aria-hidden="true">{path}</svg>'
    )


ICONS = {
    "x-lg": _bi(
        "x-lg",
        '<path d="M2.146 2.146a.5.5 0 0 1 .708 0L8 7.293l5.146-5.147a.5.5 0 0 1 '
        ".708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 "
        '5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854a.5.5 0 0 1 0-.708"/>',
    ),
    "plus-lg": _bi(
        "plus-lg",
        '<path fill-rule="evenodd" '
        'd="M8 2a.5.5 0 0 1 .5.5v5h5a.5.5 0 0 1 0 1h-5v5 '
        'a.5.5 0 0 1-1 0v-5h-5a.5.5 0 0 1 0-1h5v-5A.5.5 0 0 1 8 2"/>',
    ),
    "dash-lg": _bi(
        "dash-lg",
        '<path fill-rule="evenodd" '
        'd="M2 8a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11A.5.5 0 0 1 2 8"/>',
    ),
    "chevron-right": _bi(
        "chevron-right",
        '<path fill-rule="evenodd" '
        'd="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6 '
        'a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708"/>',
    ),
    "chevron-down": _bi(
        "chevron-down",
        '<path fill-rule="evenodd" '
        'd="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647 '
        'a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708"/>',
    ),
}

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<rect width="100" height="100" rx="18" fill="#1e1e2e"/>'
    '<text x="50" y="68" font-size="58" font-family="system-ui, -apple-system, sans-serif"'
    ' font-weight="700" text-anchor="middle" fill="#89b4fa">T</text>'
    "</svg>"
)
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(FAVICON_SVG.encode("utf-8")).decode(
    "ascii"
)

CSS = """
:root {
  --bg: #1e1e2e;
  --fg: #cdd6f4;
  --muted: #a6adc8;
  --accent: #89b4fa;
  --danger: #f38ba8;
  --code-bg: #313244;
  --border: #45475a;
  --row-alt: #262636;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.6;
}

header {
  position: sticky;
  top: 0;
  background: rgba(30, 30, 46, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  padding: 1rem 1.5rem;
  z-index: 10;
}

.header-content {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

header h1 {
  margin: 0;
  font-size: 1.5rem;
  text-align: center;
}

.search-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
}

#search {
  flex: 0 1 480px;
  min-width: 0;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: var(--code-bg);
  color: var(--fg);
  font-size: 1rem;
  text-align: center;
}

#search::placeholder { color: var(--muted); }

#search:focus {
  outline: none;
  border-color: var(--accent);
}

.controls {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.controls button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--code-bg);
  color: var(--fg);
  cursor: pointer;
}

.controls button svg {
  width: 1rem;
  height: 1rem;
}

.controls button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

main {
  max-width: 960px;
  margin: 0 auto;
  padding: 1.5rem;
}

section {
  margin-bottom: 2rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  overflow: hidden;
  scroll-margin-top: 8rem;
}

section.collapsed .section-body {
  display: none;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--code-bg);
  cursor: pointer;
  user-select: none;
}

.section-header h2 {
  margin: 0;
  font-size: 1.125rem;
  color: var(--accent);
}

.toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  line-height: 1;
  transition: transform 0.2s ease;
}

.toggle svg {
  width: 1rem;
  height: 1rem;
}

section:not(.collapsed) .toggle {
  transform: rotate(90deg);
}

.section-header[title] {
  cursor: pointer;
}

.section-body {
  padding: 0.5rem 1rem 1rem;
}

.section-body h3 {
  margin: 1.25rem 0 0.25rem;
  font-size: 1rem;
  color: var(--fg);
}

#section-jump {
  flex: 0 1 220px;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: var(--code-bg);
  color: var(--muted);
  font-size: 0.875rem;
}

#section-jump:focus {
  outline: none;
  border-color: var(--accent);
}

p {
  margin: 0.75rem 0;
}

ul {
  margin: 0.75rem 0;
  padding-left: 1.5rem;
}

li {
  margin: 0.35rem 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.5rem;
}

th, td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  word-break: break-word;
}

th {
  color: var(--accent);
  font-weight: 600;
  background: var(--row-alt);
}

tr:nth-child(even) { background: var(--row-alt); }

tbody tr.hidden { display: none; }

code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  background: var(--code-bg);
  padding: 0.125rem 0.25rem;
  border-radius: 0.25rem;
  font-size: 0.9em;
}

.danger { color: var(--danger); }

ul {
  padding-left: 1.25rem;
}

li {
  margin: 0.375rem 0;
}

.hidden { display: none; }

footer {
  text-align: center;
  padding: 2rem 1rem;
  color: var(--muted);
  font-size: 0.875rem;
}

footer a {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--muted);
  text-decoration: none;
}

footer a:hover {
  color: var(--fg);
}

footer svg {
  width: 1.25rem;
  height: 1.25rem;
}

@media print {
  :root {
    --bg: #ffffff;
    --fg: #111111;
    --muted: #555555;
    --accent: #0a4a8f;
    --danger: #b00020;
    --code-bg: #f0f0f0;
    --border: #cccccc;
    --row-alt: #f7f7f7;
  }

  header { position: static; background: #ffffff; }
  .search-row, .toggle, footer { display: none; }
  section { break-inside: avoid; }
  section.collapsed .section-body { display: block; }
}

@media (max-width: 640px) {
  header {
    padding: 1rem;
  }

  .header-content {
    text-align: left;
  }

  h1 {
    font-size: 1.5rem;
  }

  .search-row {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
  }

  #search {
    flex: 1 1 auto;
    min-width: 240px;
    font-size: 1rem;
  }

  #section-jump {
    flex: 1 1 100%;
  }

  .controls {
    justify-content: center;
  }

  main {
    padding: 1rem;
  }

  section {
    margin-bottom: 1rem;
  }

  .section-header h2 {
    font-size: 1rem;
  }

  th, td {
    padding: 0.5rem;
    font-size: 0.9375rem;
  }

  code {
    word-break: break-word;
  }
}
"""

JS = """
(function () {
  const search = document.getElementById('search');
  const clearSearch = document.getElementById('clear-search');
  const sections = Array.from(document.querySelectorAll('section'));

  const chevronRight = __CHEVRON_RIGHT_SVG__;
  const chevronDown = __CHEVRON_DOWN_SVG__;

  function updateToggleIcon(section) {
    const toggle = section.querySelector('.toggle');
    if (!toggle) return;
    toggle.innerHTML = section.classList.contains('collapsed')
      ? chevronRight
      : chevronDown;
  }

  document.querySelectorAll('.section-header').forEach(header => {
    header.addEventListener('click', () => {
      const section = header.parentElement;
      section.classList.toggle('collapsed');
      updateToggleIcon(section);
    });
  });

  function setAllCollapsed(collapsed) {
    sections.forEach(section => {
      if (section.classList.contains('hidden')) return;
      section.classList.toggle('collapsed', collapsed);
      updateToggleIcon(section);
    });
  }

  document.getElementById('expand-all').addEventListener('click', () => setAllCollapsed(false));
  document.getElementById('collapse-all').addEventListener('click', () => setAllCollapsed(true));

  clearSearch.addEventListener('click', () => {
    search.value = '';
    updateSearch();
    search.focus();
  });

  function updateSearch() {
    const query = search.value.trim().toLowerCase();
    sections.forEach(section => {
      const heading = section.querySelector('.section-header h2');
      const headingMatch =
        !!query && heading && heading.innerText.toLowerCase().includes(query);
      const rows = Array.from(section.querySelectorAll('tbody tr'));
      let sectionMatch = !query || headingMatch;

      if (rows.length > 0) {
        // A match on the section title shows the whole section unfiltered.
        rows.forEach(row => {
          const text = row.innerText.toLowerCase();
          const match = !query || headingMatch || text.includes(query);
          row.classList.toggle('hidden', !match);
          if (match) sectionMatch = true;
        });

        // A match on a subheading shows that subsection's full table.
        section.querySelectorAll('h3').forEach(sub => {
          if (!query || headingMatch) return;
          if (!sub.innerText.toLowerCase().includes(query)) return;
          const table = sub.nextElementSibling;
          if (table && table.tagName === 'TABLE') {
            table.querySelectorAll('tbody tr').forEach(row => row.classList.remove('hidden'));
            sectionMatch = true;
          }
        });

        // Hide tables (and their subheadings) that lost all rows to the filter.
        section.querySelectorAll('table').forEach(table => {
          const anyVisible = Array.from(table.querySelectorAll('tbody tr'))
            .some(row => !row.classList.contains('hidden'));
          table.classList.toggle('hidden', !anyVisible);
          const prev = table.previousElementSibling;
          if (prev && prev.tagName === 'H3') prev.classList.toggle('hidden', !anyVisible);
        });
      } else {
        const body = section.querySelector('.section-body');
        const text = body ? body.innerText.toLowerCase() : '';
        sectionMatch = !query || headingMatch || text.includes(query);
      }

      section.classList.toggle('hidden', !sectionMatch);
      if (sectionMatch && query) {
        section.classList.remove('collapsed');
        updateToggleIcon(section);
      }
    });
  }

  search.addEventListener('input', updateSearch);

  const sectionJump = document.getElementById('section-jump');
  sectionJump.addEventListener('change', () => {
    const target = document.getElementById(sectionJump.value);
    if (target) {
      target.classList.remove('collapsed');
      updateToggleIcon(target);
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    sectionJump.value = '';
  });

  document.addEventListener('keydown', event => {
    if (event.key === '/' && document.activeElement !== search) {
      event.preventDefault();
      search.focus();
    }
  });
})();
"""


def _parse_table_block(lines: list[str], start: int) -> tuple[dict | None, int]:
    """Parse a markdown table block and return parsed block + next index."""
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and lines[i].startswith("|"):
        # Split on pipes, treating `|` inside backticks as cell content.
        row_text = lines[i][1:-1]
        cells: list[str] = []
        current_cell = ""
        in_backticks = False
        for char in row_text:
            if char == "`":
                in_backticks = not in_backticks
                current_cell += char
            elif char == "|" and not in_backticks:
                cells.append(current_cell.strip())
                current_cell = ""
            else:
                current_cell += char
        cells.append(current_cell.strip())
        rows.append(cells)
        i += 1

    if len(rows) >= 2 and all(set(cell) <= {"-", ":", " "} for cell in rows[1]):
        return {"type": "table", "header": rows[0], "rows": rows[2:]}, i
    return None, i


def _parse_list_block(lines: list[str], start: int) -> tuple[dict, int]:
    """Parse a markdown bullet-list block and return parsed block + next index."""
    items: list[str] = []
    i = start
    while i < len(lines) and lines[i].startswith("- "):
        items.append(lines[i][2:].strip())
        i += 1
    return {"type": "list", "items": items}, i


def parse_markdown(md: str) -> list[dict]:
    """Parse markdown into sections with headings, paragraphs, lists, and tables."""
    sections: list[dict] = []
    current: dict | None = None
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            if current is not None:
                current["body"].append({"type": "subheading", "text": line[4:].strip()})
            i += 1
            continue
        if line.startswith("## "):
            current = {"heading": line[3:].strip(), "body": []}
            sections.append(current)
            i += 1
            continue
        if line.startswith("# "):
            i += 1
            continue
        if current is None:
            i += 1
            continue
        if line.startswith("|"):
            block, i = _parse_table_block(lines, i)
            if block is not None:
                current["body"].append(block)
                continue
        if line.startswith("- "):
            block, i = _parse_list_block(lines, i)
            current["body"].append(block)
            continue
        if line.strip():
            current["body"].append({"type": "paragraph", "text": line.strip()})
        i += 1
    return sections


def render_cell(text: str) -> str:
    """Render a table cell, escaping HTML and marking danger text."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if escaped.startswith("(!)"):
        escaped = f'<span class="danger">{escaped}</span>'
    # Wrap backtick content in <code>, preserving empty backtick pairs.
    parts = []
    for segment in re.split(r"(`[^`]*`)", escaped):
        if segment.startswith("`") and segment.endswith("`"):
            inner = segment[1:-1]
            parts.append(f"<code>{inner if inner else ' '}</code>")
        else:
            parts.append(segment)
    return "".join(parts)


def _slugify(heading: str) -> str:
    """Turn a section heading into an HTML id."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def render_sections(sections: list[dict]) -> str:
    """Render parsed sections as HTML."""
    parts: list[str] = []
    for section in sections:
        parts.append(f'<section class="collapsed" id="{_slugify(section["heading"])}">')
        header = html.escape(section["heading"])
        parts.append(
            '<div class="section-header" title="Click to expand/collapse">\n'
            f"      <h2>{header}</h2>\n"
            f'      <span class="toggle" aria-hidden="true">{ICONS["chevron-right"]}</span>\n'
            "    </div>"
        )
        parts.append('<div class="section-body">')
        for block in section["body"]:
            if block["type"] == "subheading":
                parts.append(f"<h3>{render_cell(block['text'])}</h3>")
            elif block["type"] == "paragraph":
                parts.append(f"<p>{render_cell(block['text'])}</p>")
            elif block["type"] == "list":
                parts.append("<ul>")
                for item in block["items"]:
                    parts.append(f"<li>{render_cell(item)}</li>")
                parts.append("</ul>")
            elif block["type"] == "table":
                parts.append("<table>")
                parts.append("<thead><tr>")
                for cell in block["header"]:
                    content = render_cell(cell) if cell.strip() else "&nbsp;"
                    parts.append(f"<th>{content}</th>")
                parts.append("</tr></thead><tbody>")
                for row in block["rows"]:
                    parts.append("<tr>")
                    for cell in row:
                        content = render_cell(cell) if cell.strip() else "&nbsp;"
                        parts.append(f"<td>{content}</td>")
                    parts.append("</tr>")
                parts.append("</tbody></table>")
        parts.append("</div></section>")
    return "\n".join(parts)


def render_nav(sections: list[dict]) -> str:
    """Render the section jump dropdown for the page header."""
    options = "".join(
        f'<option value="{_slugify(section["heading"])}">{html.escape(section["heading"])}</option>'
        for section in sections
    )
    return (
        '<select id="section-jump" aria-label="Jump to section">'
        f'<option value="">Jump to section...</option>{options}</select>'
    )


def render_html(md: str, title: str = "Terminal Cheat Sheet") -> str:
    """Render markdown to a complete self-contained HTML page."""
    sections = parse_markdown(md)
    nav = render_nav(sections)
    body = render_sections(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta
    name="description"
    content="Terminal cheat sheet: Linux commands, shell shortcuts, tmux and WezTerm controls."
  >
  <meta name="keywords" content="terminal, linux, commands, cheat sheet, wezterm, tmux, zsh">
  <link rel="icon" type="image/svg+xml" href="{FAVICON}">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <header>
    <div class="header-content">
      <h1>{html.escape(title)}</h1>
      <div class="search-row">
        <input
          id="search"
          type="search"
          placeholder="Search commands and shortcuts... (press / to focus)"
          autocomplete="off"
        >
        {nav}
        <div class="controls">
          <button id="clear-search" type="button" title="Clear search">
            {ICONS["x-lg"]}
          </button>
          <button id="expand-all" type="button" title="Expand all sections">
            {ICONS["plus-lg"]}
          </button>
          <button id="collapse-all" type="button" title="Collapse all sections">
            {ICONS["dash-lg"]}
          </button>
        </div>
      </div>
    </div>
  </header>
  <main>
    {body}
  </main>
  <footer>
    <a href="https://github.com/niksavis/terminal" target="_blank" rel="noopener noreferrer">
      <svg height="20" width="20" viewBox="0 0 16 16" aria-hidden="true">
        <path
          fill="currentColor"
          d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
             0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
             -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
             .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
             -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
             1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82
             1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
             1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
        />
      </svg>
      View source on GitHub
    </a>
  </footer>
  <script>{
        JS.replace("__CHEVRON_RIGHT_SVG__", json.dumps(ICONS["chevron-right"])).replace(
            "__CHEVRON_DOWN_SVG__", json.dumps(ICONS["chevron-down"])
        )
    }</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """Entry point for the renderer."""
    parser = argparse.ArgumentParser(description="Render terminal cheat sheet to HTML.")
    parser.add_argument("--input", type=Path, default=DEFAULT_MD, help="Input markdown file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_HTML, help="Output HTML file.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with error if HTML is out of date.",
    )
    args = parser.parse_args(argv)

    md_text = args.input.read_text(encoding="utf-8")
    html_text = render_html(md_text)

    if args.check:
        if not args.output.exists():
            print(f"MISSING: {args.output}", file=sys.stderr)
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing != html_text:
            print(f"OUT OF DATE: {args.output}", file=sys.stderr)
            return 1
        print(f"UP TO DATE: {args.output}")
        return 0

    args.output.write_text(html_text, encoding="utf-8")
    print(f"Rendered {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
