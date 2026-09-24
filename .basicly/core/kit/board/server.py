from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_HERE = Path(__file__).resolve().parent


TRACKER_DIR = _HERE.parent / "tracker"


def tracker_cli() -> Any:

    name = "basicly_tracker_kit_cli"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    source = TRACKER_DIR / "cli.py"
    spec = importlib.util.spec_from_file_location(name, source)
    if not source.is_file() or spec is None or spec.loader is None:
        raise SystemExit(
            f"the board kit needs the tracker kit beside it at {TRACKER_DIR}; "
            f"install it with `basicly-tracker init`"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
API = "/api/v1"
SCHEMA = "basicly.tracker.api.v1"
WEB_DIR = _HERE / "web"
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
JSON_TYPE = "application/json"
MAX_BODY_BYTES = 1_000_000

READS = ("ready", "blocked", "stats", "fields", "refine", "scaffold")
ENDPOINTS = (
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
    "POST /api/v1/records/<id>/assign  {to, take}",
    "POST /api/v1/records/<id>/claim  {to, take}",
    "POST /api/v1/records/<id>/unassign  {}",
)

_SHAPE = {"title": "--title", "description": "--description"}
_SHAPE.update(acceptance="--acceptance", requirements="--requirements")
_CREATE_KEYS = frozenset({*_SHAPE, "fields", "parent", "prefix"})
_UPDATE_KEYS = frozenset({*_SHAPE, "fields", "status", "add_labels", "remove_labels"})


class RequestError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def _refuse(message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> RequestError:
    return RequestError(status, message)


def _record(value: str) -> str:
    if not tracker_cli().ids.is_record_id(value):
        raise _refuse(f"{value!r} is not a record id")
    return value


def _query(query: dict, name: str, flag: str) -> list:
    values = query.get(name)
    return [f"{flag}={values[0]}"] if values else []


def _text(body: dict, key: str) -> str:
    value = body.get(key, "")
    if not isinstance(value, str):
        raise _refuse(f"{key} must be a string")
    return value


def _checked(body: object, allowed: frozenset) -> dict:
    if not isinstance(body, dict):
        raise _refuse("the body must be one JSON object")
    if unknown := sorted(set(body) - allowed):
        raise _refuse(f"unknown key(s) {unknown}; allowed: {sorted(allowed)}")
    return body


def _named(body: dict) -> dict:
    named = body.get("fields", {})
    if not isinstance(named, dict):
        raise _refuse("fields must map a field name to its value")
    return named


def _shape_options(body: dict) -> list:

    options = [f"{flag}={_text(body, key)}" for key, flag in _SHAPE.items() if key in body]
    options += [
        f"--field={name}={json.dumps(value)}" for name, value in sorted(_named(body).items())
    ]
    return options


def _labels(body: dict, key: str, flag: str) -> list:
    values = body.get(key, [])
    if not isinstance(values, list) or not all(isinstance(one, str) for one in values):
        raise _refuse(f"{key} must be a list of label strings")
    return [f"{flag}={one}" for one in values]


def default_prefix(ledger: Path) -> str:

    cli = tracker_cli()
    ids = cli.ids
    roots = Counter(
        record.partition(ids.PREFIX_SEP)[0]
        for record in cli.queries.folded(ledger)
        if ids.CHILD_SEP not in record
    )
    if len(roots) != 1:
        raise _refuse(
            f"name the id prefix as prefix: this ledger holds {len(roots)} root prefixes "
            f"({', '.join(sorted(roots)) or 'none'}), so none is the obvious one"
        )
    return next(iter(roots))


def read_argv(ledger: Path, path: str, query: dict) -> list:

    parts = [unquote(part) for part in path[len(API) :].strip("/").split("/") if part]
    where = str(ledger)
    if len(parts) == 1 and parts[0] in READS:
        limit = _query(query, "limit", "--limit") if parts[0] == "ready" else []
        kind = _query(query, "type", "--type") if parts[0] == "scaffold" else []
        return [parts[0], *limit, *kind, "--", where]
    if parts == ["records"]:
        filters = _query(query, "status", "--status") + _query(query, "limit", "--limit")
        return ["list", *filters, "--", where]
    if len(parts) == 2 and parts[0] == "records":
        return ["show", "--", where, _record(parts[1])]
    if len(parts) == 3 and parts[0] == "records" and parts[2] == "dor":
        return ["dor", "--", where, _record(parts[1])]
    raise _refuse(f"no read at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)


def write_argv(ledger: Path, method: str, path: str, body: object) -> list:

    parts = [unquote(part) for part in path[len(API) :].strip("/").split("/") if part]
    where = str(ledger)
    if method == "POST" and parts == ["records"]:
        held = _checked(body, _CREATE_KEYS)
        options = _shape_options(held)
        parent = _text(held, "parent")
        if parent:
            return ["child", *options, "--", where, _record(parent)]
        prefix = _text(held, "prefix") or default_prefix(ledger)
        return ["create", f"--prefix={prefix}", *options, "--", where]
    if len(parts) < 2 or parts[0] != "records":
        raise _refuse(f"no write at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)
    record = _record(parts[1])
    if method == "PATCH" and len(parts) == 2:
        held = dict(_checked(body, _UPDATE_KEYS))
        if "title" in held:
            held["fields"] = {**_named(held), "title": _text(held, "title")}
            del held["title"]
        options = _shape_options(held)
        options += [f"--status={_text(held, 'status')}"] if "status" in held else []
        options += _labels(held, "add_labels", "--add-label")
        options += _labels(held, "remove_labels", "--remove-label")
        return ["update", *options, "--", where, record]
    action = parts[2] if len(parts) == 3 else ""
    build = _ACTIONS.get(action) if method == "POST" else None
    if build is None:
        raise _refuse(f"no {method} at {path}; GET {API} lists them", HTTPStatus.NOT_FOUND)
    return build(where, record, body)


def _comment_argv(where: str, record: str, body: object) -> list:
    return ["comment", "--", where, record, _text(_checked(body, frozenset({"text"})), "text")]


def _close_argv(where: str, record: str, body: object) -> list:
    reason = _text(_checked(body, frozenset({"reason"})), "reason")
    return ["close", f"--reason={reason}", "--", where, record]


def _dep_argv(where: str, record: str, body: object) -> list:
    held = _checked(body, frozenset({"target", "type"}))
    kind = [f"--type={_text(held, 'type')}"] if "type" in held else []
    return ["dep", *kind, "--", where, record, _record(_text(held, "target"))]


def _hold_argv(action: str) -> Callable[[str, str, object], list]:

    def build(where: str, record: str, body: object) -> list:
        held = _checked(body, frozenset({"to", "take"}))
        options = [f"--to={_text(held, 'to')}"] if _text(held, "to") else []
        options += ["--take"] if held.get("take") is True else []
        return [action, *options, "--", where, record]

    return build


def _unassign_argv(where: str, record: str, body: object) -> list:
    _checked(body, frozenset())
    return ["unassign", "--", where, record]


_ACTIONS: dict[str, Callable[[str, str, object], list]] = {
    "comments": _comment_argv,
    "close": _close_argv,
    "deps": _dep_argv,
    "assign": _hold_argv("assign"),
    "claim": _hold_argv("claim"),
    "unassign": _unassign_argv,
}


def answer(argv: list, redact: Callable[[str], str] | None) -> tuple:

    cli = tracker_cli()
    try:
        args = cli.arguments.parser().parse_args(argv)
    except SystemExit:
        raise _refuse(f"the kit could not parse {argv[0]} with these values") from None
    code, report = cli.invoke(args, redact)
    if code == cli.EXIT_OK:
        created = args.command in ("create", "child")
        return (HTTPStatus.CREATED if created else HTTPStatus.OK), report
    missing = report.get("found") is False
    return (HTTPStatus.NOT_FOUND if missing else HTTPStatus.UNPROCESSABLE_ENTITY), report


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
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, report: dict) -> None:
        text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)
        self._send(status, text.encode("utf-8"), f"{JSON_TYPE}; charset=utf-8")

    def _trusted(self) -> None:

        host = _host_of(self.headers.get("Host", ""))
        if host not in LOOPBACK and host != self.bound:
            raise _refuse(f"Host {host!r} is not this server", HTTPStatus.FORBIDDEN)
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).hostname not in {host, *LOOPBACK}:
            raise _refuse(f"Origin {origin!r} may not write here", HTTPStatus.FORBIDDEN)

    def _body(self) -> object:

        if self.headers.get("Content-Type", "").split(";")[0].strip() != JSON_TYPE:
            raise _refuse(f"a write must send Content-Type {JSON_TYPE}")
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY_BYTES:
            raise _refuse(f"the body is over {MAX_BODY_BYTES} bytes")
        try:
            return json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            raise _refuse("the body is not JSON") from None

    def _handle(self, method: str) -> None:

        split = urlsplit(self.path)
        try:
            self._trusted()
            if method == "GET" and split.path.rstrip("/") == API:
                self._json(HTTPStatus.OK, {"schema": SCHEMA, "endpoints": list(ENDPOINTS)})
            elif method == "GET" and split.path.startswith(API + "/"):
                argv = read_argv(self.ledger, split.path, parse_qs(split.query))
                self._json(*answer(argv, self.redact))
            elif split.path.startswith(API + "/"):
                argv = write_argv(self.ledger, method, split.path, self._body())
                self._json(*answer(argv, self.redact))
            elif method == "GET":
                self._static(split.path)
            else:
                raise _refuse(f"no {method} at {split.path}", HTTPStatus.METHOD_NOT_ALLOWED)
        except RequestError as exc:
            self._json(exc.status, {"schema": SCHEMA, "refused": str(exc)})

    def _static(self, path: str) -> None:

        root = self.web.resolve()
        target = (root / unquote(path).lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if root not in target.parents or not target.is_file():
            raise _refuse(f"no page at {path}", HTTPStatus.NOT_FOUND)
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), kind)

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PATCH(self) -> None:
        self._handle("PATCH")


def make_server(
    ledger: Path, host: str, port: int, *, web: Path = WEB_DIR, redact: Any = None
) -> ThreadingHTTPServer:

    handler = type(
        "BoundHandler",
        (Handler,),
        {"ledger": ledger, "web": web, "bound": host, "redact": staticmethod(redact)},
    )
    return ThreadingHTTPServer((host, port), handler)


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


def run(args: Any, redact: Callable[[str], str] | None = None) -> int:

    ledger = tracker_cli().commands.resolve_ledger(args.directory)
    web = Path(args.web) if args.web else WEB_DIR
    server = make_server(ledger, args.host, args.port, web=web, redact=redact)
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
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
