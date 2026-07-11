# basicly skill collection

This directory is the source-of-truth skill catalog for terminal tooling.

- Source shape: `.basicly/skills/<skill-name>/SKILL.md`
- Projection command: `PYTHONPATH=.basicly uv run python -m basicly.cli skills-build`
- Default projection root: `.claude/skills`

## Included skills

- `tool-zsh`: shell startup and profile troubleshooting.
- `tool-tmux`: terminal multiplexing and persistent session workflows.
- `tool-git`: repository state, diffs, and safe version-control operations.
- `tool-curl`: low-level HTTP requests and header/status diagnostics.
- `tool-wget`: resilient scripted downloads with retry/resume support.
- `tool-fzf`: interactive fuzzy selection in terminal workflows.
- `tool-fd`: fast filename/path discovery (`fd` or `fdfind`).
- `tool-bat`: readable, syntax-highlighted file previews.
- `tool-ripgrep`: high-speed text and regex search across codebases.
- `tool-jq`: JSON filtering and transformation.
- `tool-yq`: YAML and config queries/edits.
- `tool-shellcheck`: static analysis for shell scripts.
- `tool-tree`: compact directory-structure visualization.
- `tool-xh`: user-friendly API testing and HTTP inspection.
- `tool-ast-grep`: AST-aware structural code search and rewrite.
- `tool-sd`: safer search-and-replace across files.
- `tool-git-delta`: enhanced syntax-highlighted diff review.
- `tool-typos`: typo detection for code and documentation.
- `tool-uv`: Python environment and dependency workflows.
- `tool-wezterm`: terminal emulator config and startup behavior.
- `tool-starship`: prompt configuration and rendering workflows.
