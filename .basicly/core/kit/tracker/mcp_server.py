from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

KIT = Path(__file__).resolve().parent
PROTOCOLS = ("2025-11-25", "2025-06-18", "2024-11-05")
MAX_MESSAGE = 1024 * 1024
JSON_ERRORS = (json.JSONDecodeError, RecursionError)


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"basicly_mcp_{name}", KIT / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ValueError("The installed tracker adapter is incomplete. Reinstall it.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Tracker:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve(strict=True)
        git = _load("git_runner")
        try:
            root = git.run(["rev-parse", "--show-toplevel"], self.repository).strip()
        except git.GitRunnerError:
            raise ValueError("--repository must name a Git working tree root.") from None
        if Path(root).resolve() != self.repository:
            raise ValueError("--repository must name a Git working tree root.")
        self.config_path = self.repository / ".basicly-tracker.toml"
        self.config_bytes = self.config_path.read_bytes() if self.config_path.is_file() else None
        self.tools = _load("mcp_tools")
        config = _load("vault_config").load(self.repository)
        self.prefix = config.prefix if config else ""
        self.vault = config is not None
        if not self.vault and not (self.repository / ".basicly" / "ledger").is_dir():
            raise ValueError("The repository has no tracker. Run basicly-tracker init first.")
        _load("bootstrap").prepare(self.repository)
        os.chdir(self.repository)
        self.cli = _load("cli")

    def call(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str):
            raise ValueError("tools/call needs a tool name and its arguments.")
        current = self.config_path.read_bytes() if self.config_path.is_file() else None
        if current != self.config_bytes:
            raise ValueError("Tracker configuration changed. Reconnect before another call.")
        argv = self.tools.arguments(
            params["name"], params.get("arguments", {}), vault=self.vault, prefix=self.prefix
        )
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                code = self.cli.main(argv)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
        try:
            report = json.loads(output.getvalue())
        except json.JSONDecodeError:
            return _result(
                {
                    "refused": "The tracker returned no JSON report. Run the CLI for diagnosis.",
                    "exit_code": code,
                },
                True,
            )
        return _result({"exit_code": code, "report": report}, code != 0)


def _result(report: dict[str, Any], failed: bool) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(report, ensure_ascii=False)}],
        "structuredContent": report,
        "isError": failed,
    }


def _error(identity: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identity, "error": {"code": code, "message": message}}


class ProtocolError(ValueError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _request(message: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ProtocolError(-32600, "Expected one JSON-RPC request object.")
    identity, method = message.get("id"), message.get("method")
    if not isinstance(method, str) or (
        "id" in message and (not isinstance(identity, (str, int)) or isinstance(identity, bool))
    ):
        raise ProtocolError(-32600, "Invalid JSON-RPC method or request id.")
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError(-32602, "Request params must be an object.")
    return method, params


class Server:
    def __init__(self, tracker: Tracker) -> None:
        self.tracker = tracker
        self.initialized = False
        self.ready = False

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.initialized:
            raise ProtocolError(-32600, "This server is already initialized.")
        if (
            not isinstance(params.get("protocolVersion"), str)
            or not isinstance(params.get("clientInfo"), dict)
            or not isinstance(params.get("capabilities"), dict)
        ):
            raise ProtocolError(
                -32602, "Initialize needs protocolVersion, clientInfo and capabilities."
            )
        self.initialized = True
        version = params["protocolVersion"]
        project = f"project {self.tracker.prefix}" if self.tracker.prefix else "the local ledger"
        return {
            "protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "basicly-tracker", "version": "1"},
            "instructions": (
                f"Tools operate only {project} in the bound repository. "
                "Inspect exit_code, report and isError. "
                "A pending or refused claim never authorizes work. "
                "After a vault claim settles, use in_progress as the status for tracker_update. "
                "Record real evidence before closing."
            ),
        }

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.tracker.call(params)
        except ValueError as exc:
            return _result({"refused": str(exc)}, True)
        except OSError:
            return _result(
                {"refused": "Tracker access failed. Check the CLI before reconnecting."}, True
            )

    def _invoke(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if not self.ready:
            raise ProtocolError(-32600, "Initialize and send notifications/initialized first.")
        if method == "tools/list":
            if params.get("cursor"):
                raise ProtocolError(-32602, "This catalog has no continuation cursor.")
            return {"tools": self.tracker.tools.catalog()}
        if method == "tools/call":
            return self._call(params)
        raise ProtocolError(-32601, "Method not found.")

    def dispatch(self, request: Any) -> dict[str, Any] | None:
        identity = None
        try:
            method, params = _request(request)
            identity = request.get("id")
            if "id" not in request:
                if method == "notifications/initialized" and self.initialized:
                    self.ready = True
                return None
            result = self._invoke(method, params)
        except ProtocolError as exc:
            return _error(identity, exc.code, str(exc))
        else:
            return {"jsonrpc": "2.0", "id": identity, "result": result}


def _invalid_constant(value: str) -> Any:
    raise json.JSONDecodeError("Nonfinite JSON numbers are invalid.", value, 0)


def serve(tracker: Tracker, source: TextIO, destination: TextIO) -> None:
    server = Server(tracker)
    while line := source.readline(MAX_MESSAGE + 1):
        if len(line) > MAX_MESSAGE:
            while line and not line.endswith("\n"):
                line = source.readline(MAX_MESSAGE + 1)
            response = _error(None, -32600, "Message exceeds the tracker transport limit.")
        else:
            try:
                response = server.dispatch(json.loads(line, parse_constant=_invalid_constant))
            except JSON_ERRORS:
                response = _error(None, -32700, "Invalid JSON message.")
        if response is not None:
            destination.write(json.dumps(response, ensure_ascii=False) + "\n")
            destination.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve tracker tools over MCP stdio.")
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        tracker = Tracker(args.repository)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"tracker: {exc}\n")
        return 2
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    serve(tracker, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
