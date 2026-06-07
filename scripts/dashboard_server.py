"""Dependency-free local server for the Agentic Factory dashboard."""

from __future__ import annotations

import json
import mimetypes
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


MAX_REQUEST_BYTES = 64 * 1024


def ensure_dependencies() -> None:
    """Kept for compatibility with older CLI checks; the stdlib server has none."""


def _provided_token(headers: Any, query: dict[str, list[str]]) -> str:
    header = headers.get("x-factory-token", "")
    if header:
        return header
    values = query.get("token", [])
    return values[0] if values else ""


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _event_bytes(event: str, data: dict[str, Any], event_id: int | None = None) -> bytes:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(data, sort_keys=True)}")
    return ("\n".join(parts) + "\n\n").encode("utf-8")


def _safe_static_path(base: Path, raw_path: str) -> Path | None:
    relative = unquote(raw_path.lstrip("/")) or "index.html"
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def create_handler(
    *,
    factory: Any,
    root: Path,
    db: str | None,
    token: str,
    control_enabled: bool,
    recent: int,
) -> type[BaseHTTPRequestHandler]:
    dist_dir = factory.PLUGIN_ROOT / "dashboard" / "dist"

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "AgenticFactoryDashboard/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path
            if path == "/api/health":
                self._require_auth(query)
                self._send_json(
                    {
                        "status": "ok",
                        "root": str(root),
                        "db": str(factory.db_path_for(root, db)),
                        "control_enabled": control_enabled,
                    }
                )
                return
            if path == "/api/snapshot":
                self._require_auth(query)
                conn = factory.connect(root, db)
                try:
                    payload = factory.collect_dashboard_snapshot(conn, root, db, recent)
                    payload["server"] = {
                        "control_enabled": control_enabled,
                        "live_terminal_supported": False,
                        "control_note": (
                            "Messages are recorded as factory events unless a future "
                            "session-backed adapter provides live delivery."
                        ),
                    }
                    self._send_json(payload)
                finally:
                    conn.close()
                return
            if path == "/api/ledger":
                self._require_auth(query)
                conn = factory.connect(root, db)
                try:
                    self._send_json({"markdown": factory.render_ledger(conn, root, recent, db)})
                finally:
                    conn.close()
                return
            if path == "/api/events/stream":
                self._require_auth(query)
                self._stream_events()
                return
            if path.startswith("/api/"):
                self._send_error(HTTPStatus.NOT_FOUND, "Not found.")
                return
            self._send_static(path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            self._require_auth(query)
            if not control_enabled:
                self._send_error(HTTPStatus.FORBIDDEN, "Dashboard control actions are disabled.")
                return

            path = parsed.path
            if path.startswith("/api/sessions/") and path.endswith("/message"):
                session_id = path.removeprefix("/api/sessions/").removesuffix("/message").strip("/")
                self._record_session_message(unquote(session_id))
                return
            if path.startswith("/api/operators/") and path.endswith("/message"):
                operator_id = path.removeprefix("/api/operators/").removesuffix("/message").strip("/")
                self._record_operator_message(unquote(operator_id))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found.")

        def _require_auth(self, query: dict[str, list[str]]) -> None:
            if not secrets.compare_digest(_provided_token(self.headers, query), token):
                raise PermissionError("Invalid or missing dashboard token.")

        def _read_json_body(self) -> dict[str, Any] | None:
            raw_length = self.headers.get("content-length", "0")
            try:
                length = int(raw_length)
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "Invalid content length.")
                return None
            if length < 0 or length > MAX_REQUEST_BYTES:
                self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
                return None
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_error(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON.")
                return None
            if not isinstance(payload, dict):
                self._send_error(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object.")
                return None
            return payload

        def _message_fields(self) -> tuple[str, str] | None:
            payload = self._read_json_body()
            if payload is None:
                return None
            message = payload.get("message", "")
            actor = payload.get("actor", "Dashboard")
            if not isinstance(message, str) or not isinstance(actor, str):
                self._send_error(HTTPStatus.BAD_REQUEST, "Message and actor must be strings.")
                return None
            return message, actor

        def _record_session_message(self, session_id: str) -> None:
            fields = self._message_fields()
            if fields is None:
                return
            message, actor = fields
            conn = factory.connect(root, db)
            try:
                run = factory.require_run(conn)
                payload = factory.record_agent_session_message(
                    conn,
                    run_id=run["id"],
                    session_id=session_id,
                    actor=actor,
                    message=message,
                )
                conn.commit()
                self._send_json({"status": "recorded", "delivery": payload["delivery"], "payload": payload})
            except factory.FactoryError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            finally:
                conn.close()

        def _record_operator_message(self, operator_id: str) -> None:
            fields = self._message_fields()
            if fields is None:
                return
            message, actor = fields
            conn = factory.connect(root, db)
            try:
                run = factory.require_run(conn)
                payload = factory.record_operator_message(
                    conn,
                    run_id=run["id"],
                    operator_id=operator_id,
                    actor=actor,
                    message=message,
                )
                conn.commit()
                self._send_json({"status": "recorded", "delivery": payload["delivery"], "payload": payload})
            except factory.FactoryError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            finally:
                conn.close()

        def _stream_events(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("x-accel-buffering", "no")
            self.end_headers()
            last_event_id = -1
            while True:
                conn = factory.connect(root, db)
                try:
                    row = conn.execute("SELECT MAX(id) AS max_id FROM events").fetchone()
                    max_id = int(row["max_id"] or 0)
                finally:
                    conn.close()
                if max_id != last_event_id:
                    last_event_id = max_id
                    chunk = _event_bytes(
                        "factory",
                        {"latest_event_id": max_id, "generated_at": factory.utc_now()},
                        max_id,
                    )
                else:
                    chunk = _event_bytes("heartbeat", {"generated_at": factory.utc_now()})
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
                time.sleep(2)

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = _json_bytes(payload)
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_static(self, path: str) -> None:
            static_path = _safe_static_path(dist_dir, path)
            if static_path is None and not path.startswith("/api/") and "." not in Path(path).name:
                static_path = dist_dir / "index.html"
            if static_path is None or not static_path.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "Not found.")
                return
            data = static_path.read_bytes()
            content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            self.send_header("cache-control", "no-cache" if static_path.name == "index.html" else "public, max-age=31536000")
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, status: HTTPStatus, detail: str) -> None:
            self._send_json({"detail": detail}, status=status)

        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except PermissionError as exc:
                self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))

    return DashboardHandler


def serve(
    *,
    factory: Any,
    root: Path,
    db: str | None,
    host: str,
    port: int,
    token: str,
    enable_control: bool,
    recent: int,
) -> int:
    handler = create_handler(
        factory=factory,
        root=root,
        db=db,
        token=token,
        control_enabled=enable_control,
        recent=recent,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        httpd.server_close()
    return 0
