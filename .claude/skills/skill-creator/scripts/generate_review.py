#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Anthropic, PBC.
# SPDX-FileComment: Modified by basicly 2026-10-02: no port kill, no xlsx, assets/ template.

import argparse
import base64
import contextlib
import json
import mimetypes
import re
import sys
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "viewer.html"

DATA_PLACEHOLDER = "__EMBEDDED_DATA__"

METADATA_FILES = {"transcript.md", "user_notes.md", "metrics.json"}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sql",
    ".r",
    ".toml",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

MIME_OVERRIDES = {
    ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_PROMPT_HEADING = re.compile(r"## Eval Prompt\n\n([\s\S]*?)(?=\n##|$)")


def get_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def find_runs(workspace: Path) -> list[dict]:
    runs: list[dict] = []
    _find_runs_recursive(workspace, workspace, runs)
    runs.sort(key=lambda r: (r.get("eval_id", float("inf")), r["id"]))
    return runs


def _find_runs_recursive(root: Path, current: Path, runs: list[dict]) -> None:
    if not current.is_dir():
        return

    outputs_dir = current / "outputs"
    if outputs_dir.is_dir():
        runs.append(build_run(root, current))
        return

    skip = {"node_modules", ".git", "__pycache__", "skill", "inputs"}
    for child in sorted(current.iterdir()):
        if child.is_dir() and child.name not in skip:
            _find_runs_recursive(root, child, runs)


def _read_json(path: Path) -> dict | None:
    with contextlib.suppress(json.JSONDecodeError, OSError):
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def prompt_and_eval_id(run_dir: Path) -> tuple[str, object]:
    for directory in (run_dir, run_dir.parent, run_dir.parent.parent):
        candidate = directory / "eval_metadata.json"
        metadata = _read_json(candidate) if candidate.exists() else None
        if metadata and metadata.get("prompt"):
            return metadata["prompt"], metadata.get("eval_id")

    for candidate in [run_dir / "transcript.md", run_dir / "outputs" / "transcript.md"]:
        if not candidate.exists():
            continue
        try:
            match = _PROMPT_HEADING.search(candidate.read_text(encoding="utf-8"))
        except OSError:
            continue
        if match and match.group(1).strip():
            return match.group(1).strip(), None

    return "(No prompt found)", None


def build_run(root: Path, run_dir: Path) -> dict:
    prompt, eval_id = prompt_and_eval_id(run_dir)
    run_id = str(run_dir.relative_to(root)).replace("/", "-").replace("\\", "-")

    outputs_dir = run_dir / "outputs"
    output_files = [
        embed_file(f)
        for f in sorted(outputs_dir.iterdir())
        if f.is_file() and f.name not in METADATA_FILES
    ]

    grading = None
    for candidate in [run_dir / "grading.json", run_dir.parent / "grading.json"]:
        grading = _read_json(candidate) if candidate.exists() else None
        if grading:
            break

    return {
        "id": run_id,
        "prompt": prompt,
        "eval_id": eval_id,
        "outputs": output_files,
        "grading": grading,
    }


def embed_file(path: Path) -> dict:
    ext = path.suffix.lower()
    mime = get_mime_type(path)

    if ext in TEXT_EXTENSIONS:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = "(Error reading file)"
        return {"name": path.name, "type": "text", "content": content}

    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return {"name": path.name, "type": "error", "content": "(Error reading file)"}
    data_uri = f"data:{mime};base64,{b64}"

    if ext in IMAGE_EXTENSIONS:
        return {"name": path.name, "type": "image", "mime": mime, "data_uri": data_uri}
    if ext == ".pdf":
        return {"name": path.name, "type": "pdf", "data_uri": data_uri}
    return {"name": path.name, "type": "binary", "mime": mime, "data_uri": data_uri}


def load_previous_iteration(workspace: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}

    feedback_map: dict[str, str] = {}
    data = _read_json(workspace / "feedback.json")
    if data:
        with contextlib.suppress(KeyError):
            feedback_map = {
                r["run_id"]: r["feedback"]
                for r in data.get("reviews", [])
                if r.get("feedback", "").strip()
            }

    for run in find_runs(workspace):
        result[run["id"]] = {
            "feedback": feedback_map.get(run["id"], ""),
            "outputs": run.get("outputs", []),
        }

    for run_id, fb in feedback_map.items():
        if run_id not in result:
            result[run_id] = {"feedback": fb, "outputs": []}

    return result


def generate_html(
    runs: list[dict],
    skill_name: str,
    previous: dict[str, dict] | None = None,
    benchmark: dict | None = None,
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    previous_feedback: dict[str, str] = {}
    previous_outputs: dict[str, list[dict]] = {}
    for run_id, data in (previous or {}).items():
        if data.get("feedback"):
            previous_feedback[run_id] = data["feedback"]
        if data.get("outputs"):
            previous_outputs[run_id] = data["outputs"]

    embedded = {
        "skill_name": skill_name,
        "runs": runs,
        "previous_feedback": previous_feedback,
        "previous_outputs": previous_outputs,
    }
    if benchmark:
        embedded["benchmark"] = benchmark

    data_json = json.dumps(embedded).replace("</", "<\\/")

    return template.replace(DATA_PLACEHOLDER, data_json)


def load_benchmark(benchmark_path: Path | None) -> dict | None:
    if benchmark_path and benchmark_path.exists():
        return _read_json(benchmark_path)
    return None


class ReviewHandler(BaseHTTPRequestHandler):
    def __init__(
        self,
        workspace: Path,
        skill_name: str,
        feedback_path: Path,
        previous: dict[str, dict],
        benchmark_path: Path | None,
        *args,
        **kwargs,
    ):
        self.workspace = workspace
        self.skill_name = skill_name
        self.feedback_path = feedback_path
        self.previous = previous
        self.benchmark_path = benchmark_path
        super().__init__(*args, **kwargs)

    def _send(self, status: int, content_type: str, content: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            runs = find_runs(self.workspace)
            benchmark = load_benchmark(self.benchmark_path)
            page = generate_html(runs, self.skill_name, self.previous, benchmark)
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))
        elif self.path == "/api/feedback":
            data = self.feedback_path.read_bytes() if self.feedback_path.exists() else b"{}"
            self._send(200, "application/json", data)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/feedback":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            self._send(500, "application/json", json.dumps({"error": str(e)}).encode())
            return
        if not isinstance(data, dict) or "reviews" not in data:
            error = {"error": "Expected JSON object with 'reviews' key"}
            self._send(500, "application/json", json.dumps(error).encode())
            return
        try:
            self.feedback_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            self._send(500, "application/json", json.dumps({"error": str(e)}).encode())
            return
        self._send(200, "application/json", b'{"ok":true}')

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        pass


def serve(port: int, handler: partial) -> HTTPServer:
    try:
        return HTTPServer(("127.0.0.1", port), handler)
    except OSError:
        return HTTPServer(("127.0.0.1", 0), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and serve eval review")
    parser.add_argument("workspace", type=Path, help="Path to workspace directory")
    parser.add_argument("--port", "-p", type=int, default=3117, help="Server port (default: 3117)")
    parser.add_argument("--skill-name", "-n", type=str, default=None, help="Skill name for header")
    parser.add_argument(
        "--previous-workspace",
        type=Path,
        default=None,
        help="Path to previous iteration's workspace (shows old outputs and feedback as context)",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=None,
        help="Path to benchmark.json to show in the Benchmark tab",
    )
    parser.add_argument(
        "--static",
        "-s",
        type=Path,
        default=None,
        help="Write standalone HTML to this path instead of starting a server",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        print(f"Error: {workspace} is not a directory", file=sys.stderr)
        sys.exit(1)

    runs = find_runs(workspace)
    if not runs:
        print(f"No runs found in {workspace}", file=sys.stderr)
        sys.exit(1)

    skill_name = args.skill_name or workspace.name.replace("-workspace", "")
    feedback_path = workspace / "feedback.json"

    previous: dict[str, dict] = {}
    if args.previous_workspace:
        previous = load_previous_iteration(args.previous_workspace.resolve())

    benchmark_path = args.benchmark.resolve() if args.benchmark else None

    if args.static:
        page = generate_html(runs, skill_name, previous, load_benchmark(benchmark_path))
        args.static.parent.mkdir(parents=True, exist_ok=True)
        args.static.write_text(page, encoding="utf-8")
        print(f"\n  Static viewer written to: {args.static}\n")
        sys.exit(0)

    handler = partial(ReviewHandler, workspace, skill_name, feedback_path, previous, benchmark_path)
    server = serve(args.port, handler)
    url = f"http://localhost:{server.server_address[1]}"
    print("\n  Eval Viewer")
    print("  ─────────────────────────────────")
    print(f"  URL:       {url}")
    print(f"  Workspace: {workspace}")
    print(f"  Feedback:  {feedback_path}")
    if previous:
        print(f"  Previous:  {args.previous_workspace} ({len(previous)} runs)")
    if benchmark_path:
        print(f"  Benchmark: {benchmark_path}")
    print("\n  Press Ctrl+C to stop.\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
