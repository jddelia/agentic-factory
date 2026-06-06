#!/usr/bin/env python3
"""SQLite-backed software factory operations.

This CLI is intentionally stdlib-only so agents can use it in most repositories
without installing project dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ".agentic-factory"
DEFAULT_DB_NAME = "factory.db"
ACTIVE_BATON_STATUSES = {"assigned", "active", "in_progress", "handed_off", "review"}


class FactoryError(RuntimeError):
    """Expected CLI failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def json_loads_or_empty(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def resolve_root(root: str | None) -> Path:
    return Path(root or os.getcwd()).expanduser().resolve()


def db_path_for(root: Path, db: str | None) -> Path:
    if db:
        path = Path(db).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.resolve()
    return root / DEFAULT_DB_DIR / DEFAULT_DB_NAME


def connect(root: Path, db: str | None = None) -> sqlite3.Connection:
    path = db_path_for(root, db)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          applied_at TEXT NOT NULL
        )
        """
    )
    migrations = sorted((PLUGIN_ROOT / "migrations").glob("*.sql"))
    for migration in migrations:
        version_text = migration.name.split("_", 1)[0]
        try:
            version = int(version_text)
        except ValueError as exc:
            raise FactoryError(f"Invalid migration filename: {migration.name}") from exc
        exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()
        if exists:
            continue
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, migration.name, utc_now()),
        )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def emit_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    actor: str = "",
    run_id: str | None = None,
    baton_id: str | None = None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO events
          (occurred_at, event_type, actor, run_id, baton_id, summary, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (utc_now(), event_type, actor, run_id, baton_id, summary, json_dump(payload or {})),
    )


def current_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM factory_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()


def require_run(conn: sqlite3.Connection) -> sqlite3.Row:
    run = current_run(conn)
    if run is None:
        raise FactoryError("No factory run exists. Run `factory.py init` first.")
    return run


def active_batons(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in ACTIVE_BATON_STATUSES)
    return list(
        conn.execute(
            f"""
            SELECT * FROM batons
            WHERE run_id = ? AND status IN ({placeholders})
            ORDER BY assigned_at DESC
            """,
            (run_id, *sorted(ACTIVE_BATON_STATUSES)),
        )
    )


def held_locks(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM locks WHERE run_id = ? AND status = 'held' ORDER BY acquired_at DESC",
            (run_id,),
        )
    )


def git_command(root: Path, args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout.strip()


def parse_json_input(raw: str | None, file_path: str | None) -> dict[str, Any]:
    if raw and file_path:
        raise FactoryError("Use either --payload or --payload-file, not both.")
    if file_path:
        raw = Path(file_path).expanduser().read_text(encoding="utf-8")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FactoryError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(value, dict):
        raise FactoryError("Payload must be a JSON object.")
    return value


def csv_values(values: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for piece in value.split(","):
            stripped = piece.strip()
            if stripped:
                result.append(stripped)
    return result


def require_baton(conn: sqlite3.Connection, baton_id: str) -> sqlite3.Row:
    baton = conn.execute("SELECT * FROM batons WHERE id = ?", (baton_id,)).fetchone()
    if baton is None:
        raise FactoryError(f"Unknown baton: {baton_id}")
    return baton


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    existing = current_run(conn)
    if existing and not args.force:
        print_json(
            {
                "status": "exists",
                "message": "Factory DB already has a run. Use --force to create another run.",
                "db": str(db_path_for(root, args.db)),
                "run": row_to_dict(existing),
            }
        )
        return 0

    now = utc_now()
    run_id = args.run_id or f"factory-{now.replace(':', '').replace('-', '').replace('Z', '')}"
    conn.execute(
        """
        INSERT INTO factory_runs
          (id, project_root, objective, work_mode, topology, status, started_at, updated_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            run_id,
            str(root),
            args.objective or "",
            args.mode,
            args.topology,
            now,
            now,
            json_dump({"created_by": "agentic-factory"}),
        ),
    )
    emit_event(
        conn,
        event_type="factory.started",
        actor=args.actor,
        run_id=run_id,
        summary=args.objective or f"Factory started in {args.mode} mode",
        payload={"work_mode": args.mode, "topology": args.topology, "project_root": str(root)},
    )
    conn.commit()
    print_json({"status": "initialized", "db": str(db_path_for(root, args.db)), "run_id": run_id})
    return 0


def collect_status(conn: sqlite3.Connection, root: Path, db: str | None = None) -> dict[str, Any]:
    run = require_run(conn)
    run_id = run["id"]
    latest_event = conn.execute(
        "SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at DESC, id DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    latest_baton = conn.execute(
        "SELECT * FROM batons WHERE run_id = ? ORDER BY assigned_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    active = active_batons(conn, run_id)
    locks = held_locks(conn, run_id)
    git_status_code, git_status = git_command(root, ["status", "-sb", "--porcelain=v1"])
    git_head_code, git_head = git_command(root, ["log", "--oneline", "-1"])
    return {
        "db": str(db_path_for(root, db)),
        "run": row_to_dict(run),
        "active_batons": [row_to_dict(row) for row in active],
        "held_locks": [row_to_dict(row) for row in locks],
        "latest_baton": row_to_dict(latest_baton),
        "latest_event": row_to_dict(latest_event),
        "git": {
            "head": git_head if git_head_code == 0 else "",
            "status": git_status if git_status_code == 0 else "",
            "available": git_status_code == 0,
        },
    }


def cmd_status(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    status = collect_status(conn, root, args.db)
    if args.json:
        print_json(status)
        return 0

    run = status["run"]
    active = status["active_batons"]
    locks = status["held_locks"]
    latest_baton = status["latest_baton"] or {}
    if args.compact:
        print(
            "\n".join(
                [
                    f"factory={run['id']} status={run['status']} mode={run['work_mode']}",
                    f"active_batons={len(active)} held_locks={len(locks)}",
                    f"latest_baton={latest_baton.get('id', 'none')} status={latest_baton.get('status', 'none')}",
                    f"git={status['git']['head'] or 'unavailable'}",
                ]
            )
        )
        return 0

    print(f"Factory: {run['id']}")
    print(f"Status: {run['status']}")
    print(f"Mode: {run['work_mode']}")
    print(f"Objective: {run['objective']}")
    print(f"Active batons: {len(active)}")
    for baton in active:
        print(f"  - {baton['id']}: {baton['title']} ({baton['status']}) owner={baton['owner']}")
    print(f"Held locks: {len(locks)}")
    for lock in locks:
        print(f"  - {lock['name']}: holder={lock['holder']} baton={lock['baton_id']}")
    if status["git"]["head"]:
        print(f"Git: {status['git']['head']}")
    return 0


def cmd_event_append(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    payload = parse_json_input(args.payload, args.payload_file)
    emit_event(
        conn,
        event_type=args.type,
        actor=args.actor,
        run_id=run["id"],
        baton_id=args.baton,
        summary=args.summary,
        payload=payload,
    )
    conn.commit()
    print_json({"status": "recorded", "event_type": args.type, "baton": args.baton})
    return 0


def acquire_lock(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    name: str,
    holder: str,
    baton_id: str | None,
    force: bool = False,
) -> None:
    existing = conn.execute(
        "SELECT * FROM locks WHERE name = ? AND status = 'held'",
        (name,),
    ).fetchone()
    if existing and not force:
        raise FactoryError(
            f"Lock `{name}` is already held by {existing['holder']} for baton {existing['baton_id']}."
        )
    if existing and force:
        conn.execute(
            "UPDATE locks SET status = 'released', released_at = ? WHERE name = ? AND status = 'held'",
            (utc_now(), name),
        )
    conn.execute(
        """
        INSERT OR REPLACE INTO locks
          (name, run_id, baton_id, holder, status, acquired_at, released_at, metadata_json)
        VALUES (?, ?, ?, ?, 'held', ?, NULL, '{}')
        """,
        (name, run_id, baton_id, holder, utc_now()),
    )


def release_lock(conn: sqlite3.Connection, *, name: str) -> None:
    conn.execute(
        "UPDATE locks SET status = 'released', released_at = ? WHERE name = ? AND status = 'held'",
        (utc_now(), name),
    )


def cmd_baton_create(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    active = active_batons(conn, run["id"])
    if active and not args.allow_active:
        active_ids = ", ".join(row["id"] for row in active)
        raise FactoryError(f"Active baton exists ({active_ids}). Use --allow-active only for non-writer records.")
    now = utc_now()
    conn.execute(
        """
        INSERT INTO batons
          (id, run_id, title, owner, owner_thread, status, scope, acceptance_tier,
           verification_level, model, reasoning, assigned_at, summary, metadata_json)
        VALUES (?, ?, ?, ?, ?, 'assigned', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.baton_id,
            run["id"],
            args.title,
            args.owner,
            args.owner_thread or "",
            args.scope or "",
            args.acceptance_tier,
            args.verification_level,
            args.model or "",
            args.reasoning or "",
            now,
            args.summary or "",
            json_dump({"created_by": args.actor}),
        ),
    )
    if not args.no_lock:
        acquire_lock(
            conn,
            run_id=run["id"],
            name=args.lock_name,
            holder=args.owner or args.actor,
            baton_id=args.baton_id,
            force=args.force_lock,
        )
    emit_event(
        conn,
        event_type="baton.assigned",
        actor=args.actor,
        run_id=run["id"],
        baton_id=args.baton_id,
        summary=args.title,
        payload={
            "owner": args.owner,
            "scope": args.scope,
            "acceptance_tier": args.acceptance_tier,
            "verification_level": args.verification_level,
            "lock_acquired": not args.no_lock,
        },
    )
    conn.commit()
    print_json({"status": "assigned", "baton": args.baton_id, "lock": None if args.no_lock else args.lock_name})
    return 0


def cmd_baton_handoff(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    baton = require_baton(conn, args.baton_id)
    files = csv_values(args.files)
    commands = csv_values(args.commands)
    verification = csv_values(args.verification)
    now = utc_now()
    payload = {
        "owner": args.owner,
        "files_changed": files,
        "commands_run": commands,
        "verification": verification,
    }
    conn.execute(
        """
        UPDATE batons
        SET status = 'handed_off', handed_off_at = ?, summary = ?, metadata_json = ?
        WHERE id = ?
        """,
        (now, args.summary, json_dump({**json_loads_or_empty(baton["metadata_json"], {}), "handoff": payload}), args.baton_id),
    )
    conn.execute(
        """
        INSERT INTO handoffs
          (baton_id, files_changed_json, behavior_changed, commands_run_json, verification_json,
           risks, next_recommended, created_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.baton_id,
            json_dump(files),
            args.behavior or "",
            json_dump(commands),
            json_dump(verification),
            args.risks or "",
            args.next or "",
            now,
            json_dump(payload),
        ),
    )
    if args.release_lock:
        release_lock(conn, name=args.lock_name)
    emit_event(
        conn,
        event_type="baton.handed_off",
        actor=args.owner or args.actor,
        run_id=run["id"],
        baton_id=args.baton_id,
        summary=args.summary,
        payload=payload,
    )
    conn.commit()
    print_json({"status": "handed_off", "baton": args.baton_id, "lock_released": args.release_lock})
    return 0


def cmd_baton_accept(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    baton = require_baton(conn, args.baton_id)
    now = utc_now()
    conn.execute(
        """
        UPDATE batons
        SET status = 'accepted', accepted_at = ?, commit_sha = ?, summary = ?
        WHERE id = ?
        """,
        (now, args.commit or "", args.summary or baton["summary"], args.baton_id),
    )
    if args.commit:
        conn.execute(
            """
            INSERT INTO commits (baton_id, sha, message, pushed_status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (args.baton_id, args.commit, args.message or "", args.pushed_status, now),
        )
    if args.release_lock:
        release_lock(conn, name=args.lock_name)
    emit_event(
        conn,
        event_type="baton.accepted",
        actor=args.actor,
        run_id=run["id"],
        baton_id=args.baton_id,
        summary=args.summary or "Baton accepted",
        payload={"commit": args.commit or "", "pushed_status": args.pushed_status},
    )
    conn.commit()
    print_json({"status": "accepted", "baton": args.baton_id, "commit": args.commit or ""})
    return 0


def cmd_verify_record(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    if args.baton:
        require_baton(conn, args.baton)
    if args.result not in {"pass", "fail", "not_run", "blocked"}:
        raise FactoryError("--result must be one of pass, fail, not_run, blocked")
    if args.duration_ms is not None and args.duration_ms < 0:
        raise FactoryError("--duration-ms must be greater than or equal to 0")
    conn.execute(
        """
        INSERT INTO verification_runs
          (baton_id, command, package_name, result, duration_ms, summary, created_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.baton,
            args.command,
            args.package or "",
            args.result,
            args.duration_ms,
            args.summary or "",
            utc_now(),
            json_dump(parse_json_input(args.payload, args.payload_file)),
        ),
    )
    emit_event(
        conn,
        event_type="verification.completed",
        actor=args.actor,
        run_id=run["id"],
        baton_id=args.baton,
        summary=f"{args.result}: {args.command}",
        payload={"result": args.result, "command": args.command, "package": args.package or ""},
    )
    conn.commit()
    print_json({"status": "recorded", "result": args.result, "command": args.command})
    return 0


def parse_finding(raw: str) -> dict[str, Any]:
    parts = raw.split("|", 4)
    if len(parts) != 5:
        raise FactoryError(
            "Finding must use format severity|file|line|status|summary"
        )
    severity, file_name, line_text, status, summary = [part.strip() for part in parts]
    line: int | None
    if not line_text or line_text == "0":
        line = None
    else:
        try:
            line = int(line_text)
        except ValueError as exc:
            raise FactoryError(f"Invalid finding line: {line_text}") from exc
    return {
        "severity": severity,
        "file": file_name,
        "line": line,
        "status": status,
        "summary": summary,
    }


def cmd_review_record(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    require_baton(conn, args.baton)
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO reviews
          (baton_id, reviewer, reviewer_thread, status, summary, created_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.baton,
            args.reviewer,
            args.reviewer_thread or "",
            args.status,
            args.summary or "",
            now,
            json_dump(parse_json_input(args.payload, args.payload_file)),
        ),
    )
    review_id = int(cur.lastrowid)
    findings = [parse_finding(raw) for raw in args.finding or []]
    for finding in findings:
        conn.execute(
            """
            INSERT INTO review_findings
              (review_id, severity, file, line, status, summary, resolution, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, '', '{}')
            """,
            (
                review_id,
                finding["severity"],
                finding["file"],
                finding["line"],
                finding["status"],
                finding["summary"],
            ),
        )
    emit_event(
        conn,
        event_type="review.recorded",
        actor=args.reviewer or args.actor,
        run_id=run["id"],
        baton_id=args.baton,
        summary=args.summary or f"Review {args.status}",
        payload={"review_id": review_id, "findings": findings},
    )
    conn.commit()
    print_json({"status": "recorded", "review_id": review_id, "findings": len(findings)})
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    now = utc_now()
    conn.execute(
        """
        UPDATE factory_runs
        SET status = 'paused', paused_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, run["id"]),
    )
    emit_event(
        conn,
        event_type="factory.paused",
        actor=args.actor,
        run_id=run["id"],
        summary=args.reason or f"Paused with mode {args.mode}",
        payload={"mode": args.mode, "reason": args.reason or ""},
    )
    conn.commit()
    print_json({"status": "paused", "mode": args.mode, "reason": args.reason or ""})
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    now = utc_now()
    conn.execute(
        """
        UPDATE factory_runs
        SET status = 'active', resumed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, run["id"]),
    )
    emit_event(
        conn,
        event_type="factory.resumed",
        actor=args.actor,
        run_id=run["id"],
        summary=args.reason or "Factory resumed",
        payload={"reason": args.reason or ""},
    )
    conn.commit()
    print_json({"status": "active", "reason": args.reason or ""})
    return 0


def cmd_lock_acquire(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    acquire_lock(
        conn,
        run_id=run["id"],
        name=args.name,
        holder=args.holder,
        baton_id=args.baton,
        force=args.force,
    )
    emit_event(
        conn,
        event_type="lock.acquired",
        actor=args.holder,
        run_id=run["id"],
        baton_id=args.baton,
        summary=f"{args.name} acquired by {args.holder}",
        payload={"lock": args.name},
    )
    conn.commit()
    print_json({"status": "held", "lock": args.name, "holder": args.holder})
    return 0


def cmd_lock_release(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    release_lock(conn, name=args.name)
    emit_event(
        conn,
        event_type="lock.released",
        actor=args.actor,
        run_id=run["id"],
        summary=f"{args.name} released",
        payload={"lock": args.name},
    )
    conn.commit()
    print_json({"status": "released", "lock": args.name})
    return 0


def render_ledger(conn: sqlite3.Connection, root: Path, recent: int, db: str | None = None) -> str:
    status = collect_status(conn, root, db)
    run = status["run"]
    batons = list(
        conn.execute(
            "SELECT * FROM batons WHERE run_id = ? ORDER BY assigned_at DESC LIMIT ?",
            (run["id"], recent),
        )
    )
    events = list(
        conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (run["id"], recent),
        )
    )
    lines = [
        "# Build Ledger",
        "",
        "<!-- Generated by Agentic Factory. Prefer structured DB events for updates. -->",
        "",
        "## Current Factory State",
        "",
        "```text",
        f"Factory status: {run['status']}",
        f"Project root: {run['project_root']}",
        f"Operating mode: {run['work_mode']}",
        f"Topology: {run['topology']}",
        f"Objective: {run['objective']}",
        f"Active batons: {len(status['active_batons'])}",
        f"Held locks: {len(status['held_locks'])}",
        f"Git head: {status['git']['head'] or 'unavailable'}",
        "```",
        "",
        "## Active Batons",
        "",
    ]
    if status["active_batons"]:
        lines.extend(["| Baton | Title | Owner | Status |", "| --- | --- | --- | --- |"])
        for baton in status["active_batons"]:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (baton["id"], baton["title"], baton["owner"], baton["status"])
                )
                + " |"
            )
    else:
        lines.append("No active batons.")
    lines.extend(["", "## Recent Batons", ""])
    if batons:
        lines.extend(["| Baton | Status | Title | Commit | Updated |", "| --- | --- | --- | --- | --- |"])
        for baton in batons:
            updated = baton["accepted_at"] or baton["handed_off_at"] or baton["assigned_at"]
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        baton["id"],
                        baton["status"],
                        baton["title"],
                        baton["commit_sha"],
                        updated,
                    )
                )
                + " |"
            )
    else:
        lines.append("No batons recorded.")
    lines.extend(["", "## Recent Events", ""])
    if events:
        lines.extend(["| Time | Type | Baton | Summary |", "| --- | --- | --- | --- |"])
        for event in events:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        event["occurred_at"],
                        event["event_type"],
                        event["baton_id"] or "",
                        event["summary"],
                    )
                )
                + " |"
            )
    else:
        lines.append("No events recorded.")
    lines.append("")
    return "\n".join(lines)


def cmd_render_ledger(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    if args.recent < 1:
        raise FactoryError("--recent must be greater than 0")
    markdown = render_ledger(conn, root, args.recent, args.db)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print_json({"status": "rendered", "out": str(out), "recent": args.recent})
    else:
        print(markdown)
    return 0


def doctor_check(root: Path, conn: sqlite3.Connection) -> tuple[list[dict[str, str]], int]:
    findings: list[dict[str, str]] = []
    exit_code = 0

    def add(level: str, check: str, message: str) -> None:
        nonlocal exit_code
        findings.append({"level": level, "check": check, "message": message})
        if level == "fail":
            exit_code = 1

    run = require_run(conn)
    active = active_batons(conn, run["id"])
    locks = held_locks(conn, run["id"])
    add("ok", "schema", "SQLite schema is present")
    if len(active) > 1:
        add("fail", "active_batons", f"More than one active baton: {', '.join(row['id'] for row in active)}")
    else:
        add("ok", "active_batons", f"{len(active)} active baton(s)")
    if len(locks) > 1:
        add("fail", "locks", f"More than one held lock: {', '.join(row['name'] for row in locks)}")
    else:
        add("ok", "locks", f"{len(locks)} held lock(s)")

    code, output = git_command(root, ["status", "--short", "--untracked-files=all"])
    if code == 0:
        if output.strip():
            add("warn", "git_dirty", "Worktree has changes")
        else:
            add("ok", "git_dirty", "Worktree is clean")
    else:
        add("warn", "git", "Git status unavailable")

    protected = root / "apps/web/next-env.d.ts"
    if protected.exists():
        diff_code, _ = git_command(root, ["diff", "--exit-code", "--", "apps/web/next-env.d.ts"])
        staged_code, staged = git_command(root, ["diff", "--cached", "--name-only", "--", "apps/web/next-env.d.ts"])
        if diff_code != 0 or (staged_code == 0 and staged.strip()):
            add("fail", "protected_next_env", "apps/web/next-env.d.ts has diff or is staged")
        else:
            add("ok", "protected_next_env", "apps/web/next-env.d.ts is unchanged")

    ahead_code, ahead = git_command(root, ["status", "-sb"])
    if ahead_code == 0:
        add("ok", "branch", ahead.splitlines()[0] if ahead else "Branch status available")
    return findings, exit_code


def cmd_doctor(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    findings, exit_code = doctor_check(root, conn)
    if args.json:
        print_json({"status": "fail" if exit_code else "ok", "findings": findings})
    else:
        for finding in findings:
            print(f"[{finding['level']}] {finding['check']}: {finding['message']}")
    return exit_code


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=None, help="Project root; defaults to current directory.")
    parser.add_argument("--db", default=None, help="Factory DB path; defaults to .agentic-factory/factory.db.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite-backed software factory CLI.")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize a factory DB.")
    init.add_argument("--mode", default="balanced")
    init.add_argument("--objective", default="")
    init.add_argument("--topology", default="executive_as_ledger")
    init.add_argument("--actor", default="Agent")
    init.add_argument("--run-id", default="")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    status = subparsers.add_parser("status", help="Show current factory state.")
    status.add_argument("--json", action="store_true")
    status.add_argument("--compact", action="store_true")
    status.set_defaults(func=cmd_status)

    event = subparsers.add_parser("event", help="Record a raw event.")
    event_sub = event.add_subparsers(dest="event_command", required=True)
    event_append = event_sub.add_parser("append", help="Append a structured event.")
    event_append.add_argument("--type", required=True)
    event_append.add_argument("--actor", default="Agent")
    event_append.add_argument("--baton", default=None)
    event_append.add_argument("--summary", default="")
    event_append.add_argument("--payload", default=None)
    event_append.add_argument("--payload-file", default=None)
    event_append.set_defaults(func=cmd_event_append)

    baton = subparsers.add_parser("baton", help="Create, hand off, or accept batons.")
    baton_sub = baton.add_subparsers(dest="baton_command", required=True)
    baton_create = baton_sub.add_parser("create", help="Assign a baton and acquire the writer lock.")
    baton_create.add_argument("baton_id")
    baton_create.add_argument("--title", required=True)
    baton_create.add_argument("--owner", default="Builder")
    baton_create.add_argument("--owner-thread", default="")
    baton_create.add_argument("--scope", default="")
    baton_create.add_argument("--summary", default="")
    baton_create.add_argument("--acceptance-tier", default="integration")
    baton_create.add_argument("--verification-level", default="focused")
    baton_create.add_argument("--model", default="")
    baton_create.add_argument("--reasoning", default="")
    baton_create.add_argument("--actor", default="Executive")
    baton_create.add_argument("--allow-active", action="store_true")
    baton_create.add_argument("--no-lock", action="store_true")
    baton_create.add_argument("--lock-name", default="main-worktree")
    baton_create.add_argument("--force-lock", action="store_true")
    baton_create.set_defaults(func=cmd_baton_create)

    baton_handoff = baton_sub.add_parser("handoff", help="Record a baton handoff.")
    baton_handoff.add_argument("baton_id")
    baton_handoff.add_argument("--owner", default="Builder")
    baton_handoff.add_argument("--summary", required=True)
    baton_handoff.add_argument("--behavior", default="")
    baton_handoff.add_argument("--files", action="append", default=[])
    baton_handoff.add_argument("--commands", action="append", default=[])
    baton_handoff.add_argument("--verification", action="append", default=[])
    baton_handoff.add_argument("--risks", default="")
    baton_handoff.add_argument("--next", default="")
    baton_handoff.add_argument("--actor", default="Builder")
    baton_handoff.add_argument("--release-lock", action="store_true", default=True)
    baton_handoff.add_argument("--keep-lock", dest="release_lock", action="store_false")
    baton_handoff.add_argument("--lock-name", default="main-worktree")
    baton_handoff.set_defaults(func=cmd_baton_handoff)

    baton_accept = baton_sub.add_parser("accept", help="Accept a baton.")
    baton_accept.add_argument("baton_id")
    baton_accept.add_argument("--commit", default="")
    baton_accept.add_argument("--message", default="")
    baton_accept.add_argument("--pushed-status", default="unknown")
    baton_accept.add_argument("--summary", default="")
    baton_accept.add_argument("--actor", default="Executive")
    baton_accept.add_argument("--release-lock", action="store_true", default=True)
    baton_accept.add_argument("--keep-lock", dest="release_lock", action="store_false")
    baton_accept.add_argument("--lock-name", default="main-worktree")
    baton_accept.set_defaults(func=cmd_baton_accept)

    verify = subparsers.add_parser("verify", help="Record verification commands.")
    verify_sub = verify.add_subparsers(dest="verify_command", required=True)
    verify_record = verify_sub.add_parser("record")
    verify_record.add_argument("--baton", default=None)
    verify_record.add_argument("--command", required=True)
    verify_record.add_argument("--result", required=True)
    verify_record.add_argument("--package", default="")
    verify_record.add_argument("--duration-ms", type=int, default=None)
    verify_record.add_argument("--summary", default="")
    verify_record.add_argument("--actor", default="Agent")
    verify_record.add_argument("--payload", default=None)
    verify_record.add_argument("--payload-file", default=None)
    verify_record.set_defaults(func=cmd_verify_record)

    review = subparsers.add_parser("review", help="Record review packets.")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_record = review_sub.add_parser("record")
    review_record.add_argument("--baton", required=True)
    review_record.add_argument("--reviewer", default="Reviewer")
    review_record.add_argument("--reviewer-thread", default="")
    review_record.add_argument("--status", default="recorded")
    review_record.add_argument("--summary", default="")
    review_record.add_argument("--finding", action="append", default=[])
    review_record.add_argument("--actor", default="Reviewer")
    review_record.add_argument("--payload", default=None)
    review_record.add_argument("--payload-file", default=None)
    review_record.set_defaults(func=cmd_review_record)

    pause = subparsers.add_parser("pause", help="Pause the factory.")
    pause.add_argument("--mode", default="drain_to_checkpoint")
    pause.add_argument("--reason", default="")
    pause.add_argument("--actor", default="Executive")
    pause.set_defaults(func=cmd_pause)

    resume = subparsers.add_parser("resume", help="Resume the factory.")
    resume.add_argument("--reason", default="")
    resume.add_argument("--actor", default="Executive")
    resume.set_defaults(func=cmd_resume)

    lock = subparsers.add_parser("lock", help="Manage explicit locks.")
    lock_sub = lock.add_subparsers(dest="lock_command", required=True)
    lock_acquire = lock_sub.add_parser("acquire")
    lock_acquire.add_argument("--name", default="main-worktree")
    lock_acquire.add_argument("--holder", required=True)
    lock_acquire.add_argument("--baton", default=None)
    lock_acquire.add_argument("--force", action="store_true")
    lock_acquire.set_defaults(func=cmd_lock_acquire)
    lock_release = lock_sub.add_parser("release")
    lock_release.add_argument("--name", default="main-worktree")
    lock_release.add_argument("--actor", default="Agent")
    lock_release.set_defaults(func=cmd_lock_release)

    render = subparsers.add_parser("render-ledger", help="Render markdown ledger from DB.")
    render.add_argument("--out", default="")
    render.add_argument("--recent", type=int, default=20)
    render.set_defaults(func=cmd_render_ledger)

    doctor = subparsers.add_parser("doctor", help="Run factory health checks.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FactoryError as exc:
        print(f"factory: error: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"factory: database error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
