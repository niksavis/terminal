# Machine-readable documentation routes

A route tells you what a release documents. It does not tell you what the installed command does. Probe a route before you quote it. Follow redirects. Read an unexpected redirect or a 404 as a moved route, not as a missing fact.

| Dependency | Route |
| --- | --- |
| uv | `docs.astral.sh/uv/llms.txt`; one page: `docs.astral.sh/uv/<page>/index.md` |
| ruff | `docs.astral.sh/ruff/llms.txt`; one page: `docs.astral.sh/ruff/<page>/index.md` |
| Claude Code | `code.claude.com/docs/llms.txt`; one page: `code.claude.com/docs/en/<slug>.md` |
| Anthropic API | `platform.claude.com/llms.txt`; one page: `platform.claude.com/docs/en/<path>.md`. Never fetch the whole `llms-full.txt`, which is very large |
| Codex | `developers.openai.com/codex/llms.txt`, which redirects to `learn.chatgpt.com/docs/llms.txt`; one page: `learn.chatgpt.com/docs/<slug>.md` |
| GitHub Docs (Copilot CLI, Actions) | `docs.github.com/llms.txt`; append `.md` to any page URL for markdown |
| Python | no `llms.txt`; `docs.python.org/3/_sources/<path>.rst.txt` and `docs.python.org/3/objects.inv` |
| pytest | no `llms.txt`; `docs.pytest.org/en/stable/_sources/<path>.rst.txt` and `docs.pytest.org/en/stable/objects.inv` |
| git, pre-commit | none; run `<tool> <cmd> --help` on the installed binary |
| any other dependency | probe `<docs-host>/llms.txt`, then the Sphinx pair `objects.inv` and `_sources/<path>.rst.txt`, else the installed binary |

The GitHub Docs Search API refuses a request with no `client_name` parameter. The error is `Missing required parameter 'client_name' for external requests`. Add `&client_name=<a name for this tool>` to every GitHub Docs API request.
