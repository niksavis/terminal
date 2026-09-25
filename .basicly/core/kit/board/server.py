from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import mimetypes
import os
import sys
from collections.abc import Callable, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the board kit's {file_name} is missing from beside server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


routes = _load("routes.py", "basicly_board_kit_routes")
RequestError = routes.RequestError
tracker_cli = routes.tracker_cli
API = routes.API


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SCHEMA = "basicly.tracker.api.v1"
WEB_DIR = _HERE / "web"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_PORT = 65535
WINSOCK_ADDRESS_IN_USE = 10048
ADDRESS_IN_USE = frozenset({errno.EADDRINUSE, WINSOCK_ADDRESS_IN_USE})
EXIT_PORT_IN_USE = 1
JSON_TYPE = "application/json"
MAX_BODY_BYTES = 1_000_000

ENDPOINTS = (
    "GET  /api/v1/version",
    "GET  /api/v1/ready?limit=N",
    "GET  /api/v1/blocked",
    "GET  /api/v1/stats",
    "GET  /api/v1/fields",
    "GET  /api/v1/refine",
    "GET  /api/v1/scaffold?type=T",
    "GET  /api/v1/records?status=S&limit=N",
    "GET  /api/v1/records/<id>",
    "GET  /api/v1/records/<id>/dor",
    "POST /api/v1/records  {title, description, acceptance, requirements, fields, parent, prefix}",
    "PATCH /api/v1/records/<id>  {title, description, acceptance, requirements, fields, status, "
    "add_labels, remove_labels}",
    "POST /api/v1/records/<id>/comments  {text}",
    "POST /api/v1/records/<id>/close  {reason}",
    "POST /api/v1/records/<id>/deps  {target, type}",
    "POST /api/v1/records/<id>/undep  {target, type}",
    "POST /api/v1/records/<id>/assign  {to, take}",
    "POST /api/v1/records/<id>/claim  {to, take}",
    "POST /api/v1/records/<id>/unassign  {}",
)


def api_index(ledger: Path) -> dict:

    commands = tracker_cli().commands
    return {
        "schema": SCHEMA,
        "endpoints": list(ENDPOINTS),
        "holder": commands.holders.default_holder(ledger),
        "edge_types": sorted(commands.differential.DEFAULT_VOCABULARY.edge_types),
    }


def api_version(ledger: Path) -> dict:

    stamps = []
    for path in tracker_cli().events.ledger_paths(ledger):
        try:
            held = path.stat()
        except OSError:
            continue
        stamps.append((path.name, held.st_size, held.st_mtime_ns))
    return {"schema": SCHEMA, "version": format(hash(tuple(stamps)) & (2**64 - 1), "016x")}


def answer(argv: list, redact: Callable[[str], str] | None, *, read: bool = False) -> tuple:

    cli = tracker_cli()
    try:
        args = cli.arguments.parser().parse_args(argv)
    except SystemExit:
        raise routes.refuse(f"the kit could not parse {argv[0]} with these values") from None
    code, report = cli.invoke(args, redact)
    if code == cli.EXIT_OK:
        created = args.command in ("create", "child")
        return (HTTPStatus.CREATED if created else HTTPStatus.OK), report
    missing = report.get("found") is False
    if missing:
        return HTTPStatus.NOT_FOUND, report
    verdict = read and not isinstance(report.get("refused"), str)
    return (HTTPStatus.OK if verdict else HTTPStatus.UNPROCESSABLE_ENTITY), report


def _host_of(header: str) -> str:
    if header.startswith("["):
        return header[1:].partition("]")[0]
    return header.rpartition(":")[0] if header.count(":") == 1 else header


class Handler(BaseHTTPRequestHandler):
    ledger: Path = Path()
    web: Path = WEB_DIR
    bound: str = "127.0.0.1"
    redact: Any = None

    def _send(self, status: HTTPStatus, body: bytes, kind: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError) as error:
            closed = "the client closed the connection before %s answered: %s"
            self.log_message(closed, self.path, error)

    def _json(self, status: HTTPStatus, report: dict) -> None:
        text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)
        self._send(status, text.encode("utf-8"), f"{JSON_TYPE}; charset=utf-8")

    def _trusted(self) -> None:

        host = _host_of(self.headers.get("Host", ""))
        if host not in LOOPBACK and host != self.bound:
            raise routes.refuse(f"Host {host!r} is not this server", HTTPStatus.FORBIDDEN)
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).hostname not in {host, *LOOPBACK}:
            raise routes.refuse(f"Origin {origin!r} may not write here", HTTPStatus.FORBIDDEN)

    def _body(self) -> object:

        if self.headers.get("Content-Type", "").split(";")[0].strip() != JSON_TYPE:
            raise routes.refuse(f"a write must send Content-Type {JSON_TYPE}")
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY_BYTES:
            raise routes.refuse(f"the body is over {MAX_BODY_BYTES} bytes")
        self.consumed = True
        try:
            return json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            raise routes.refuse("the body is not JSON") from None

    def _drain(self) -> None:

        if getattr(self, "consumed", False):
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < size <= MAX_BODY_BYTES:
            self.rfile.read(size)
        self.consumed = True

    def _handle(self, method: str) -> None:

        split = urlsplit(self.path)
        try:
            self._trusted()
            if method == "GET" and split.path.rstrip("/") == API:
                self._json(HTTPStatus.OK, api_index(self.ledger))
            elif method == "GET" and split.path.rstrip("/") == API + "/version":
                self._json(HTTPStatus.OK, api_version(self.ledger))
            elif method == "GET" and split.path.startswith(API + "/"):
                argv = routes.read_argv(self.ledger, split.path, parse_qs(split.query))
                self._json(*answer(argv, self.redact, read=True))
            elif split.path.startswith(API + "/"):
                argv = routes.write_argv(self.ledger, method, split.path, self._body())
                self._json(*answer(argv, self.redact))
            elif method == "GET":
                self._static(split.path)
            else:
                raise routes.refuse(f"no {method} at {split.path}", HTTPStatus.METHOD_NOT_ALLOWED)
        except RequestError as exc:
            self._drain()
            self._json(exc.status, {"schema": SCHEMA, "refused": str(exc)})

    def _static(self, path: str) -> None:

        root = self.web.resolve()
        target = (root / unquote(path).lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if root not in target.parents or not target.is_file():
            raise routes.refuse(f"no page at {path}", HTTPStatus.NOT_FOUND)
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), kind)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")


class LookupFreeServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        super(HTTPServer, self).server_bind()


def make_server(
    ledger: Path, host: str, port: int, *, web: Path = WEB_DIR, redact: Any = None
) -> ThreadingHTTPServer:

    handler = type(
        "BoundHandler",
        (Handler,),
        {"ledger": ledger, "web": web, "bound": host, "redact": staticmethod(redact)},
    )
    return LookupFreeServer((host, port), handler)


def address_in_use(error: OSError) -> bool:
    return error.errno in ADDRESS_IN_USE


def busy_port_refusal(host: str, port: int, relaunch: str) -> str:

    other = port + 1 if port < MAX_PORT else DEFAULT_PORT
    return (
        f"board: port {port} is in use on {host}, so nothing was served; start it on another "
        f"port with `{relaunch} --port {other}`, or with `--port 0` to let the system choose "
        "a free one"
    )


def relaunch(program: str, directory: str) -> str:

    starts = f"python3 {program}" if program.endswith(".py") else Path(program).name
    return f"{starts} serve {directory}"


def parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description="Serve the tracker board page and its HTTP API on localhost."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    served = sub.add_parser("serve", help="serve the page and the API until Ctrl+C")
    served.add_argument("directory", help="the ledger directory")
    served.add_argument("--host", default=DEFAULT_HOST, help="the address to bind")
    served.add_argument("--port", type=int, default=DEFAULT_PORT, help="the port to bind")
    served.add_argument("--web", default="", help="serve your own page directory instead")
    return parser


def serve_as_a_person(environ: Any = os.environ) -> None:

    writers = tracker_cli().commands.writers
    for marker in (*writers.AGENT_MARKERS, writers.CLAUDE_CODE_MARKER):
        environ.pop(marker, None)


def run(args: Any, redact: Callable[[str], str] | None = None) -> int:

    serve_as_a_person()
    ledger = tracker_cli().commands.resolve_ledger(args.directory)
    web = Path(args.web) if args.web else WEB_DIR
    try:
        server = make_server(ledger, args.host, args.port, web=web, redact=redact)
    except OSError as error:
        if not address_in_use(error):
            raise
        bound = "" if args.host == DEFAULT_HOST else f" --host {args.host}"
        sys.stderr.write(busy_port_refusal(args.host, args.port, args.relaunch + bound) + "\n")
        return EXIT_PORT_IN_USE
    host, port = server.server_address[:2]
    if args.host not in LOOPBACK:
        sys.stderr.write(f"board: {args.host} is not loopback; the network can write\n")
    sys.stderr.write(f"board: http://{host}:{port}/ serves {ledger}; API at {API}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("board: stopped\n")
    finally:
        server.server_close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.relaunch = relaunch(sys.argv[0], args.directory)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
