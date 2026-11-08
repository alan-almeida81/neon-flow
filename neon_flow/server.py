"""Local HTTP server for the Neon Flow console (read-only).

GET /            -> the console (web/index.html); add ?demo=1 for the built-in simulation
GET /api/flow    -> the flow projection (see docs/CONTRATO-DE-DADOS.md)
GET /api/terminal-stream?terminalId=<uuid> -> one terminal's output as Server-Sent Events (read-only)
GET /vendor/xterm/xterm.js|xterm.css       -> the bundled xterm.js used by the terminal viewer
POST /api/prompt {terminalId, text}         -> sends what the operator typed to that terminal (local only)
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .flow import build_flow

PAGE = Path(__file__).resolve().parent.parent / "web" / "index.html"
VENDOR = {"/vendor/xterm/xterm.js": "text/javascript; charset=utf-8", "/vendor/xterm/xterm.css": "text/css; charset=utf-8"}


def read_json(path: Path | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def maestri_routines() -> dict:
    """Scheduling metadata of Maestri routines, if present; never the commands themselves."""
    try:
        saved = json.loads((Path.home() / ".maestri" / "routines.json").read_text(encoding="utf-8"))
        return {"items": [{key: item.get(key) for key in (
            "id", "name", "workspaceId", "terminalId", "isEnabled", "schedule", "createdAt", "lastFiredAt", "skipIfBusy",
        )} for item in saved["payload"]], "error": None}
    except (OSError, ValueError, KeyError, TypeError):
        return {"items": [], "error": "Agendamentos locais indisponíveis"}


class FlowSource:
    """Builds /api/flow from a snapshot source plus optional runtime and board JSON files, with small caches."""

    def __init__(self, snapshot_file: Path | None = None, runtime_file: Path | None = None, board_file: Path | None = None):
        self.snapshot_file, self.runtime_file, self.board_file = snapshot_file, runtime_file, board_file
        self.lock, self.cache, self.memory = threading.Lock(), {}, {}

    def _cached(self, key, ttl, load):
        at, value = self.cache.get(key, (0, None))
        if time.monotonic() - at > ttl:
            value = load()
            self.cache[key] = (time.monotonic(), value)
        return value

    def _snapshot(self):
        if self.snapshot_file:
            return read_json(self.snapshot_file)
        from .wire import feed
        return feed()

    def _runtime(self):
        runtime = read_json(self.runtime_file)
        runtime.setdefault("routines", maestri_routines())
        return runtime

    def _board(self):
        try:
            return read_json(self.board_file)
        except (OSError, ValueError) as exc:
            return {"lists": [], "cards": [], "error": f"Quadro indisponível: {type(exc).__name__}"}

    def flow(self) -> dict:
        with self.lock:
            snapshot = self._cached("snapshot", 3, self._snapshot)
            runtime = self._cached("runtime", 5, self._runtime)
            board = self._cached("board", 30, self._board)
            return build_flow(snapshot, runtime, board, self.memory)


def make_handler(source: FlowSource, allowed_hosts: set[str]):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body: bytes, kind: str):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            if host not in allowed_hosts:   # blocks DNS rebinding from other sites
                self.send_error(403)
                return
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).hostname not in allowed_hosts:   # no cross-site reads
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path in ("/", "/fluxo", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path in VENDOR:
                self._send(200, (PAGE.parent / path.lstrip("/")).read_bytes(), VENDOR[path])
            elif path == "/api/terminal-stream":
                from .terminal import stream_terminal
                terminal = parse_qs(urlsplit(self.path).query).get("terminalId", [""])[0]
                try:
                    stream_terminal(self, terminal)
                except Exception as exc:   # before the stream starts: a JSON error, never a traceback
                    self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            elif path == "/api/flow":
                try:
                    body, status = source.flow(), 200
                except Exception as exc:   # surface the reason, never a traceback
                    body, status = {"error": f"{type(exc).__name__}: {exc}"}, 503
                self._send(status, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            # Only one write exists: a prompt the operator typed in the terminal viewer, sent through Wire.
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            origin = self.headers.get("Origin")
            if (host not in allowed_hosts or (origin and urlsplit(origin).hostname not in allowed_hosts)
                    or not ipaddress.ip_address(self.client_address[0]).is_loopback
                    or not self.headers.get("Content-Type", "").startswith("application/json")):
                self.send_error(403)   # same machine, same page, JSON only (forms from other sites cannot post)
                return
            if urlsplit(self.path).path != "/api/prompt":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if size > 100_000:
                    raise ValueError("Prompt grande demais.")
                body = json.loads(self.rfile.read(size) or b"{}")
                terminal, text = str(UUID(str(body.get("terminalId", "")))), body.get("text", "")
                if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
                    raise ValueError("Informe um prompt de até 20 mil caracteres.")
                from .wire import send_prompt
                result = send_prompt(terminal, text)
                self._send(200, json.dumps(result if isinstance(result, dict) else {"ok": True}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, format, *args):
            pass

    return Handler


def serve(port: int = 8770, source: FlowSource | None = None) -> None:
    source = source or FlowSource()
    handler = make_handler(source, {"localhost", "127.0.0.1"})
    print(f"Neon Flow: http://127.0.0.1:{port}/  (simulação: http://127.0.0.1:{port}/?demo=1)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
