"""Optional FastAPI server for the Agentic Factory dashboard."""

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any


def _import_fastapi() -> dict[str, Any]:
    try:
        from fastapi import Depends, FastAPI, HTTPException, Request
        from fastapi.responses import FileResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
        import uvicorn
    except ImportError as exc:  # pragma: no cover - exercised through CLI error path.
        raise ImportError("FastAPI dashboard dependencies are not installed.") from exc
    return {
        "Depends": Depends,
        "FastAPI": FastAPI,
        "FileResponse": FileResponse,
        "HTTPException": HTTPException,
        "Request": Request,
        "StaticFiles": StaticFiles,
        "StreamingResponse": StreamingResponse,
        "uvicorn": uvicorn,
    }


def ensure_dependencies() -> None:
    _import_fastapi()


def _provided_token(request: Any) -> str:
    header = request.headers.get("x-factory-token", "")
    if header:
        return header
    return request.query_params.get("token", "")


def create_app(
    *,
    factory: Any,
    root: Path,
    db: str | None,
    token: str,
    enable_control: bool,
    recent: int,
) -> Any:
    deps = _import_fastapi()
    Depends = deps["Depends"]
    FastAPI = deps["FastAPI"]
    FileResponse = deps["FileResponse"]
    HTTPException = deps["HTTPException"]
    Request = deps["Request"]
    StaticFiles = deps["StaticFiles"]
    StreamingResponse = deps["StreamingResponse"]

    app = FastAPI(
        title="Agentic Factory Dashboard",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    dist_dir = factory.PLUGIN_ROOT / "dashboard" / "dist"
    assets_dir = dist_dir / "assets"

    def require_auth(request: Request) -> None:
        if not secrets.compare_digest(_provided_token(request), token):
            raise HTTPException(status_code=401, detail="Invalid or missing dashboard token.")

    def open_conn() -> Any:
        return factory.connect(root, db)

    @app.get("/api/health")
    def health(_: None = Depends(require_auth)) -> dict[str, Any]:
        return {
            "status": "ok",
            "root": str(root),
            "db": str(factory.db_path_for(root, db)),
            "control_enabled": enable_control,
        }

    @app.get("/api/snapshot")
    def snapshot(_: None = Depends(require_auth)) -> dict[str, Any]:
        conn = open_conn()
        try:
            payload = factory.collect_dashboard_snapshot(conn, root, db, recent)
            payload["server"] = {
                "control_enabled": enable_control,
                "live_terminal_supported": False,
                "control_note": (
                    "Messages are recorded as factory events unless a future session-backed "
                    "adapter provides live delivery."
                ),
            }
            return payload
        finally:
            conn.close()

    @app.get("/api/ledger")
    def ledger(_: None = Depends(require_auth)) -> dict[str, Any]:
        conn = open_conn()
        try:
            return {"markdown": factory.render_ledger(conn, root, recent, db)}
        finally:
            conn.close()

    @app.post("/api/sessions/{session_id}/message")
    async def session_message(session_id: str, request: Request, _: None = Depends(require_auth)) -> dict[str, Any]:
        if not enable_control:
            raise HTTPException(status_code=403, detail="Dashboard control actions are disabled.")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object.")
        message = body.get("message", "")
        actor = body.get("actor", "Dashboard")
        if not isinstance(message, str) or not isinstance(actor, str):
            raise HTTPException(status_code=400, detail="Message and actor must be strings.")
        conn = open_conn()
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
            return {"status": "recorded", "delivery": payload["delivery"], "payload": payload}
        except factory.FactoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/api/events/stream")
    async def events_stream(request: Request, _: None = Depends(require_auth)) -> Any:
        async def generate() -> Any:
            last_event_id = 0
            while not await request.is_disconnected():
                conn = open_conn()
                try:
                    row = conn.execute("SELECT MAX(id) AS max_id FROM events").fetchone()
                    max_id = int(row["max_id"] or 0)
                finally:
                    conn.close()
                if max_id != last_event_id:
                    last_event_id = max_id
                    data = json.dumps({"latest_event_id": max_id, "generated_at": factory.utc_now()})
                    yield f"event: factory\nid: {max_id}\ndata: {data}\n\n"
                else:
                    yield f"event: heartbeat\ndata: {json.dumps({'generated_at': factory.utc_now()})}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(generate(), media_type="text/event-stream")

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    def index() -> Any:
        return FileResponse(dist_dir / "index.html")

    @app.get("/{path:path}")
    def spa_fallback(path: str) -> Any:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        return FileResponse(dist_dir / "index.html")

    return app


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
    deps = _import_fastapi()
    app = create_app(
        factory=factory,
        root=root,
        db=db,
        token=token,
        enable_control=enable_control,
        recent=recent,
    )
    deps["uvicorn"].run(app, host=host, port=port, log_level="info")
    return 0
