#!/usr/bin/env python3
"""SQLite-backed software factory operations.

This CLI is intentionally stdlib-only so agents can use it in most repositories
without installing project dependencies.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
from pathlib import PurePosixPath
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_DIR = ".agentic-factory"
DEFAULT_DB_NAME = "factory.db"
DEFAULT_CONFIG_NAME = "config.json"
ACTIVE_BATON_STATUSES = {"assigned", "active", "in_progress", "handed_off", "review"}
VERIFICATION_RESULTS = {"pass", "fail", "not_run", "blocked"}
AGENT_PACKET_ROLES = {"builder", "reviewer", "executive"}
AGENT_PACKET_FORMATS = {"markdown", "json"}
AGENT_PACKET_RUNTIME_MODES = {
    "codex_native",
    "agent_cli_subagents",
    "serial_single_agent",
    "manual_protocol",
    "adapter_spawn",
}
AGENT_PACKET_WRITE_POLICIES = {"auto", "read-only", "write"}
AGENT_SPAWN_ADAPTERS = {"codex-cli", "custom"}
CODEX_SPAWN_SANDBOXES = {"auto", "read-only", "workspace-write"}
CODEX_APPROVAL_POLICIES = {"never", "on-request", "untrusted", "on-failure"}
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 500
DEFAULT_SPAWN_TIMEOUT_SECONDS = 1800
MAX_SPAWN_TIMEOUT_SECONDS = 86400
DEFAULT_SPAWN_OUTPUT_LIMIT = 20000
MAX_SPAWN_OUTPUT_LIMIT = 200000
DEFAULT_PACKET_DIR = ".agentic-factory/packets"
DEFAULT_PROJECT_CONFIG: dict[str, Any] = {
    "default_mode": "balanced",
    "default_topology": "executive_as_ledger",
    "default_lock_name": "main-worktree",
    "ledger_output_path": "",
    "verification_policy": {
        "default_level": "focused",
        "require_baton": False,
        "require_summary_for_not_run": False,
    },
    "protected_generated_files": [],
}
CONFIG_FILE_TEMPLATE: dict[str, Any] = {
    "default_mode": "balanced",
    "default_topology": "executive_as_ledger",
    "default_lock_name": "main-worktree",
    "ledger_output_path": "docs/build_ledger.md",
    "verification_policy": {
        "default_level": "focused",
        "require_baton": False,
        "require_summary_for_not_run": True,
    },
    "protected_generated_files": [],
}


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


def config_path_for(root: Path, config: str | None) -> Path:
    if config:
        path = Path(config).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.resolve()
    return root / DEFAULT_DB_DIR / DEFAULT_CONFIG_NAME


def safe_relative_path(
    raw: Any,
    *,
    field: str,
    allow_empty: bool = False,
    label: str = "Config field",
) -> str:
    if not isinstance(raw, str):
        raise FactoryError(f"{label} `{field}` must be a string.")
    stripped = raw.strip()
    if not stripped:
        if allow_empty:
            return ""
        raise FactoryError(f"{label} `{field}` must not be empty.")
    candidate = PurePosixPath(stripped.replace("\\", "/"))
    if candidate.is_absolute() or candidate.as_posix() == "." or ".." in candidate.parts:
        raise FactoryError(f"{label} `{field}` must be a relative path inside the project.")
    return candidate.as_posix()


def require_config_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FactoryError(f"Config field `{key}` must be a non-empty string.")
    return value.strip()


def require_config_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise FactoryError(f"Config field `verification_policy.{key}` must be a boolean.")
    return value


def load_project_config(root: Path, config: str | None = None) -> tuple[dict[str, Any], Path, bool]:
    path = config_path_for(root, config)
    effective = copy.deepcopy(DEFAULT_PROJECT_CONFIG)
    if not path.is_file():
        return effective, path, False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FactoryError(f"Invalid config JSON at {path}: {exc}") from exc
    except OSError as exc:
        raise FactoryError(f"Unable to read config at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FactoryError("Project config must contain a JSON object.")

    allowed = {
        "default_mode",
        "default_topology",
        "default_lock_name",
        "ledger_output_path",
        "verification_policy",
        "protected_generated_files",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise FactoryError(f"Unknown config field(s): {', '.join(unknown)}")

    for key in ("default_mode", "default_topology", "default_lock_name"):
        if key in payload:
            effective[key] = require_config_string(payload, key)

    if "ledger_output_path" in payload:
        effective["ledger_output_path"] = safe_relative_path(
            payload["ledger_output_path"],
            field="ledger_output_path",
            allow_empty=True,
        )

    if "protected_generated_files" in payload:
        protected = payload["protected_generated_files"]
        if not isinstance(protected, list):
            raise FactoryError("Config field `protected_generated_files` must be an array.")
        effective["protected_generated_files"] = [
            safe_relative_path(value, field="protected_generated_files[]")
            for value in protected
        ]

    if "verification_policy" in payload:
        policy = payload["verification_policy"]
        if not isinstance(policy, dict):
            raise FactoryError("Config field `verification_policy` must be an object.")
        allowed_policy = {"default_level", "require_baton", "require_summary_for_not_run"}
        unknown_policy = sorted(set(policy) - allowed_policy)
        if unknown_policy:
            raise FactoryError(
                f"Unknown config field(s) under `verification_policy`: {', '.join(unknown_policy)}"
            )
        if "default_level" in policy:
            effective["verification_policy"]["default_level"] = require_config_string(policy, "default_level")
        if "require_baton" in policy:
            effective["verification_policy"]["require_baton"] = require_config_bool(policy, "require_baton")
        if "require_summary_for_not_run" in policy:
            effective["verification_policy"]["require_summary_for_not_run"] = require_config_bool(
                policy,
                "require_summary_for_not_run",
            )

    return effective, path, True


def config_for_args(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    config, _, _ = load_project_config(root, getattr(args, "config", None))
    return config


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


def parse_json_field(raw: str | None) -> Any:
    fallback: Any = [] if raw and raw.strip().startswith("[") else {}
    return json_loads_or_empty(raw, fallback)


def row_to_public_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        if key.endswith("_json"):
            payload[key[:-5]] = parse_json_field(value)
    return payload


def require_limit(value: int, *, field: str) -> int:
    if value < 1:
        raise FactoryError(f"--{field} must be greater than 0")
    if value > MAX_LIST_LIMIT:
        raise FactoryError(f"--{field} must be less than or equal to {MAX_LIST_LIMIT}")
    return value


def shorten(value: Any, max_len: int = 80) -> str:
    text = "" if value is None else str(value).replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], *, empty: str) -> None:
    if not rows:
        print(empty)
        return
    widths = {
        key: min(
            max(len(label), *(len(shorten(row.get(key), 80)) for row in rows)),
            80,
        )
        for key, label in columns
    }
    print("  ".join(label.ljust(widths[key]) for key, label in columns))
    print("  ".join("-" * widths[key] for key, _label in columns))
    for row in rows:
        print("  ".join(shorten(row.get(key), widths[key]).ljust(widths[key]) for key, _label in columns))


def shell_join(parts: Iterable[Any]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts if part is not None and str(part) != "")


def truncate_text(value: str | None, limit: int) -> tuple[str, bool]:
    text = value or ""
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n...[truncated]", True


def safe_slug(value: str | None, *, fallback: str = "none") -> str:
    text = (value or fallback).strip() or fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return (slug or fallback)[:80]


def command_prefix(root: Path, args: argparse.Namespace) -> list[str]:
    parts = ["python3", str(Path(__file__).resolve()), "--root", str(root)]
    db = getattr(args, "db", None)
    config = getattr(args, "config", None)
    if db:
        parts.extend(["--db", db])
    if config:
        parts.extend(["--config", config])
    return parts


def require_timeout(value: int) -> int:
    if value < 1:
        raise FactoryError("--timeout-seconds must be greater than 0")
    if value > MAX_SPAWN_TIMEOUT_SECONDS:
        raise FactoryError(f"--timeout-seconds must be less than or equal to {MAX_SPAWN_TIMEOUT_SECONDS}")
    return value


def require_output_limit(value: int) -> int:
    if value < 1:
        raise FactoryError("--output-limit must be greater than 0")
    if value > MAX_SPAWN_OUTPUT_LIMIT:
        raise FactoryError(f"--output-limit must be less than or equal to {MAX_SPAWN_OUTPUT_LIMIT}")
    return value


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


def clean_values(values: Iterable[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if value.strip()]


def unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            result.append(stripped)
    return result


def require_baton(conn: sqlite3.Connection, baton_id: str) -> sqlite3.Row:
    baton = conn.execute("SELECT * FROM batons WHERE id = ?", (baton_id,)).fetchone()
    if baton is None:
        raise FactoryError(f"Unknown baton: {baton_id}")
    return baton


def require_current_baton(conn: sqlite3.Connection, run: sqlite3.Row, baton_id: str) -> sqlite3.Row:
    baton = require_baton(conn, baton_id)
    if baton["run_id"] != run["id"]:
        raise FactoryError(f"Baton {baton_id} does not belong to current run {run['id']}.")
    return baton


def markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = config_for_args(root, args)
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
    work_mode = args.mode or config["default_mode"]
    topology = args.topology or config["default_topology"]
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
            work_mode,
            topology,
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
        summary=args.objective or f"Factory started in {work_mode} mode",
        payload={"work_mode": work_mode, "topology": topology, "project_root": str(root)},
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


def cmd_config_init(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    path = config_path_for(root, args.config)
    if path.exists() and not args.force:
        print_json(
            {
                "status": "exists",
                "path": str(path),
                "message": "Project config already exists. Use --force to overwrite it.",
            }
        )
        return 0
    config = copy.deepcopy(CONFIG_FILE_TEMPLATE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print_json({"status": "created", "path": str(path), "config": config})
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config, path, exists = load_project_config(root, args.config)
    print_json({"path": str(path), "exists": exists, "config": config})
    return 0


def cmd_baton_list(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    limit = require_limit(args.limit, field="limit")
    statuses = csv_values(args.status)
    params: list[Any] = [run["id"]]
    where = ["run_id = ?"]
    if statuses:
        where.append(f"status IN ({','.join('?' for _ in statuses)})")
        params.extend(statuses)
    elif not args.all:
        active = sorted(ACTIVE_BATON_STATUSES)
        where.append(f"status IN ({','.join('?' for _ in active)})")
        params.extend(active)
    params.append(limit)
    rows = list(
        conn.execute(
            f"""
            SELECT * FROM batons
            WHERE {' AND '.join(where)}
            ORDER BY assigned_at DESC
            LIMIT ?
            """,
            params,
        )
    )
    batons = [row_to_public_dict(row) for row in rows]
    if args.json:
        print_json({"count": len(batons), "batons": batons})
        return 0
    print_table(
        [baton for baton in batons if baton is not None],
        [
            ("id", "Baton"),
            ("status", "Status"),
            ("title", "Title"),
            ("owner", "Owner"),
            ("assigned_at", "Assigned"),
            ("commit_sha", "Commit"),
        ],
        empty="No batons found.",
    )
    return 0


def review_with_findings(conn: sqlite3.Connection, review: sqlite3.Row) -> dict[str, Any]:
    payload = row_to_public_dict(review) or {}
    findings = list(
        conn.execute(
            "SELECT * FROM review_findings WHERE review_id = ? ORDER BY id",
            (review["id"],),
        )
    )
    payload["findings"] = [row_to_public_dict(row) for row in findings]
    return payload


def collect_baton_detail(
    conn: sqlite3.Connection,
    run: sqlite3.Row,
    baton_id: str,
    *,
    recent_events: int,
) -> dict[str, Any]:
    baton = require_current_baton(conn, run, baton_id)
    handoffs = list(
        conn.execute(
            "SELECT * FROM handoffs WHERE baton_id = ? ORDER BY created_at DESC",
            (baton_id,),
        )
    )
    verification = list(
        conn.execute(
            "SELECT * FROM verification_runs WHERE baton_id = ? ORDER BY created_at DESC",
            (baton_id,),
        )
    )
    reviews = list(
        conn.execute(
            "SELECT * FROM reviews WHERE baton_id = ? ORDER BY created_at DESC, id DESC",
            (baton_id,),
        )
    )
    commits = list(
        conn.execute(
            "SELECT * FROM commits WHERE baton_id = ? ORDER BY created_at DESC",
            (baton_id,),
        )
    )
    events = list(
        conn.execute(
            """
            SELECT * FROM events
            WHERE baton_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (baton_id, recent_events),
        )
    )
    return {
        "baton": row_to_public_dict(baton),
        "handoffs": [row_to_public_dict(row) for row in handoffs],
        "verification": [row_to_public_dict(row) for row in verification],
        "reviews": [review_with_findings(conn, row) for row in reviews],
        "commits": [row_to_public_dict(row) for row in commits],
        "events": [row_to_public_dict(row) for row in events],
    }


def cmd_baton_show(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    recent_events = require_limit(args.recent_events, field="recent-events")
    payload = collect_baton_detail(conn, run, args.baton_id, recent_events=recent_events)
    if args.json:
        print_json(payload)
        return 0
    baton_payload = payload["baton"] or {}
    print(f"Baton: {baton_payload.get('id')}")
    print(f"Status: {baton_payload.get('status')}")
    print(f"Title: {baton_payload.get('title')}")
    print(f"Owner: {baton_payload.get('owner')}")
    print(f"Scope: {baton_payload.get('scope')}")
    print(f"Acceptance tier: {baton_payload.get('acceptance_tier')}")
    print(f"Verification level: {baton_payload.get('verification_level')}")
    if baton_payload.get("commit_sha"):
        print(f"Commit: {baton_payload.get('commit_sha')}")
    print("")
    print_table(
        [row for row in payload["verification"] if row is not None],
        [("created_at", "Time"), ("result", "Result"), ("command", "Command"), ("summary", "Summary")],
        empty="No verification records.",
    )
    print("")
    print_table(
        [row for row in payload["reviews"] if row is not None],
        [("created_at", "Time"), ("status", "Status"), ("reviewer", "Reviewer"), ("summary", "Summary")],
        empty="No review records.",
    )
    print("")
    print_table(
        [row for row in payload["events"] if row is not None],
        [("occurred_at", "Time"), ("event_type", "Type"), ("actor", "Actor"), ("summary", "Summary")],
        empty="No events.",
    )
    return 0


def cmd_events_list(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    recent = require_limit(args.recent, field="recent")
    where = ["run_id = ?"]
    params: list[Any] = [run["id"]]
    if args.baton:
        require_baton(conn, args.baton)
        where.append("baton_id = ?")
        params.append(args.baton)
    if args.type:
        where.append("event_type = ?")
        params.append(args.type)
    params.append(recent)
    rows = list(
        conn.execute(
            f"""
            SELECT * FROM events
            WHERE {' AND '.join(where)}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            params,
        )
    )
    events = [row_to_public_dict(row) for row in rows]
    if args.json:
        print_json({"count": len(events), "events": events})
        return 0
    print_table(
        [event for event in events if event is not None],
        [
            ("id", "ID"),
            ("occurred_at", "Time"),
            ("event_type", "Type"),
            ("baton_id", "Baton"),
            ("actor", "Actor"),
            ("summary", "Summary"),
        ],
        empty="No events found.",
    )
    return 0


def cmd_verification_list(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    recent = require_limit(args.recent, field="recent")
    params: list[Any]
    if args.baton:
        require_baton(conn, args.baton)
        where = "v.baton_id = ?"
        params = [args.baton, recent]
    else:
        where = "(v.baton_id IS NULL OR b.run_id = ?)"
        params = [run["id"], recent]
    rows = list(
        conn.execute(
            f"""
            SELECT v.*
            FROM verification_runs v
            LEFT JOIN batons b ON b.id = v.baton_id
            WHERE {where}
            ORDER BY v.created_at DESC, v.id DESC
            LIMIT ?
            """,
            params,
        )
    )
    verification = [row_to_public_dict(row) for row in rows]
    if args.json:
        print_json({"count": len(verification), "verification": verification})
        return 0
    print_table(
        [row for row in verification if row is not None],
        [
            ("id", "ID"),
            ("created_at", "Time"),
            ("baton_id", "Baton"),
            ("result", "Result"),
            ("command", "Command"),
            ("summary", "Summary"),
        ],
        empty="No verification records found.",
    )
    return 0


def cmd_review_list(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    conn = connect(root, args.db)
    run = require_run(conn)
    recent = require_limit(args.recent, field="recent")
    if args.baton:
        require_baton(conn, args.baton)
        where = "r.baton_id = ?"
        params: list[Any] = [args.baton, recent]
    else:
        where = "b.run_id = ?"
        params = [run["id"], recent]
    rows = list(
        conn.execute(
            f"""
            SELECT r.*
            FROM reviews r
            JOIN batons b ON b.id = r.baton_id
            WHERE {where}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ?
            """,
            params,
        )
    )
    reviews = [review_with_findings(conn, row) for row in rows]
    if args.json:
        print_json({"count": len(reviews), "reviews": reviews})
        return 0
    print_table(
        reviews,
        [
            ("id", "ID"),
            ("created_at", "Time"),
            ("baton_id", "Baton"),
            ("status", "Status"),
            ("reviewer", "Reviewer"),
            ("summary", "Summary"),
        ],
        empty="No reviews found.",
    )
    for review in reviews:
        findings = review.get("findings") or []
        if findings:
            print("")
            print(f"Findings for review {review['id']}:")
            print_table(
                findings,
                [
                    ("severity", "Severity"),
                    ("file", "File"),
                    ("line", "Line"),
                    ("status", "Status"),
                    ("summary", "Summary"),
                ],
                empty="No findings.",
            )
    return 0


def verification_check_defaults(level: str) -> list[str]:
    checks = {
        "smoke": ["Run the smallest check that proves the primary path still starts or loads."],
        "focused": ["Run focused checks that cover the baton scope."],
        "focused_plus_build": [
            "Run focused checks that cover the baton scope.",
            "Run the relevant build, type, or lint gate for changed areas.",
        ],
        "full_gate": ["Run the repository's full test, lint, type, and build gate."],
        "release_gate": [
            "Run the repository's full test, lint, type, and build gate.",
            "Run release-specific smoke or deployment-readiness checks.",
        ],
    }
    return checks.get(level, [f"Run checks appropriate for verification level `{level}`."])


def worker_policy_for(role: str, write_policy: str) -> dict[str, Any]:
    if write_policy == "write":
        may_edit = True
    elif write_policy == "read-only":
        may_edit = False
    else:
        may_edit = role == "builder"
    return {
        "write_policy": "write" if may_edit else "read-only",
        "may_edit_files": may_edit,
        "may_run_commands": role in {"builder", "reviewer", "executive"},
        "may_record_cli_evidence": True,
        "must_return_evidence_if_cli_unavailable": True,
        "reviewer_read_only_by_default": role == "reviewer",
    }


def handoff_schema_for(role: str) -> dict[str, Any]:
    if role == "builder":
        return {
            "baton_id": "string",
            "owner": "string",
            "base_commit": "string",
            "files_changed": ["path"],
            "behavior_changed": "string",
            "commands_run": ["command"],
            "passing": ["check"],
            "failing": ["check"],
            "not_run_and_why": ["check: reason"],
            "risks": "string",
            "residual_gaps": "string",
            "next_recommended_step": "string",
        }
    if role == "reviewer":
        return {
            "baton_id": "string",
            "reviewer": "string",
            "status": "accepted | patch_required | rejected | escalated",
            "summary": "string",
            "findings": ["severity|file|line|status|summary"],
            "verification_observed": ["check"],
            "recommendation": "accept | patch | reject | escalate",
            "residual_risks": "string",
        }
    return {
        "baton_id": "string",
        "decision": "accepted | patch_required | rejected | escalated",
        "acceptance_tier": "prototype | integration | release",
        "evidence": ["verification or review record"],
        "skipped_checks": ["check: reason"],
        "residual_risk": "string",
        "commit": "sha",
        "push_status": "unknown | local_only | pushed",
        "next_baton": "string",
    }


def recording_commands_for(
    *,
    prefix: list[str],
    role: str,
    baton_id: str | None,
    recent: int,
) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    if role == "builder" and baton_id:
        commands.extend(
            [
                {
                    "name": "record_verification",
                    "when": "after running a required check",
                    "command": shell_join(
                        [
                            *prefix,
                            "verify",
                            "record",
                            "--baton",
                            baton_id,
                            "--command",
                            "<command run>",
                            "--result",
                            "pass",
                            "--summary",
                            "<verification summary>",
                        ]
                    ),
                },
                {
                    "name": "record_handoff",
                    "when": "after scoped implementation and verification evidence are ready",
                    "command": shell_join(
                        [
                            *prefix,
                            "baton",
                            "handoff",
                            baton_id,
                            "--summary",
                            "<handoff summary>",
                            "--files",
                            "<file1,file2>",
                            "--commands",
                            "<command run>",
                            "--verification",
                            "<check: pass>",
                            "--risks",
                            "<risks or none>",
                            "--next",
                            "<next recommended step>",
                        ]
                    ),
                },
            ]
        )
    elif role == "reviewer" and baton_id:
        commands.extend(
            [
                {
                    "name": "record_accepted_review",
                    "when": "after read-only review finds no blocking issues",
                    "command": shell_join(
                        [
                            *prefix,
                            "review",
                            "record",
                            "--baton",
                            baton_id,
                            "--reviewer",
                            "Reviewer",
                            "--status",
                            "accepted",
                            "--summary",
                            "<review summary>",
                        ]
                    ),
                },
                {
                    "name": "record_review_with_finding",
                    "when": "after read-only review finds a required patch",
                    "command": shell_join(
                        [
                            *prefix,
                            "review",
                            "record",
                            "--baton",
                            baton_id,
                            "--reviewer",
                            "Reviewer",
                            "--status",
                            "patch_required",
                            "--summary",
                            "<review summary>",
                            "--finding",
                            "P2|path/to/file.py|123|open|Finding summary",
                        ]
                    ),
                },
            ]
        )
    else:
        commands.extend(
            [
                {
                    "name": "inspect_status",
                    "when": "before assigning or accepting work",
                    "command": shell_join([*prefix, "status", "--compact"]),
                },
                {
                    "name": "run_doctor",
                    "when": "before assigning or accepting work",
                    "command": shell_join([*prefix, "doctor"]),
                },
                {
                    "name": "list_batons",
                    "when": "to choose the next baton or inspect active work",
                    "command": shell_join([*prefix, "baton", "list", "--all"]),
                },
                {
                    "name": "list_recent_events",
                    "when": "to inspect recent state transitions",
                    "command": shell_join([*prefix, "events", "list", "--recent", recent]),
                },
                {
                    "name": "create_next_baton",
                    "when": "after choosing the next scoped unit of work",
                    "command": shell_join(
                        [
                            *prefix,
                            "baton",
                            "create",
                            "<baton id>",
                            "--title",
                            "<baton title>",
                            "--owner",
                            "Builder",
                            "--scope",
                            "<baton scope>",
                            "--acceptance-tier",
                            "integration",
                            "--verification-level",
                            "<verification level>",
                        ]
                    ),
                },
            ]
        )
        if baton_id:
            commands.append(
                {
                    "name": "accept_baton",
                    "when": "only after acceptance tier is satisfied",
                    "command": shell_join(
                        [
                            *prefix,
                            "baton",
                            "accept",
                            baton_id,
                            "--commit",
                            "<commit sha>",
                            "--pushed-status",
                            "local_only",
                            "--summary",
                            "<acceptance summary>",
                        ]
                    ),
                }
            )
        commands.append(
            {
                "name": "render_ledger",
                "when": "when a human-readable snapshot is useful",
                "command": shell_join([*prefix, "render-ledger", "--recent", recent]),
            }
        )
    return commands


def role_instructions(role: str) -> str:
    if role == "builder":
        return (
            "Implement only the scoped baton, run required checks, record verification and "
            "handoff evidence when safe, and return a compact handoff bundle if CLI access is unavailable."
        )
    if role == "reviewer":
        return (
            "Review the baton evidence and changed scope without editing files unless explicitly authorized; "
            "record or return findings and an acceptance recommendation."
        )
    return (
        "Coordinate the factory, preserve role boundaries, inspect state, route review, accept only after "
        "the selected tier is satisfied, and record durable decisions."
    )


def packet_scope(
    *,
    role: str,
    baton: dict[str, Any] | None,
    config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    allowed = csv_values(args.allowed)
    restricted = csv_values(args.restricted)
    non_goals = clean_values(args.non_goal)
    invariants = [
        "Preserve user changes; do not revert unknown work.",
        "Do not broaden the baton scope silently.",
        "Respect sandbox, credential, destructive-action, and external-effect boundaries.",
    ]
    protected_files = config["protected_generated_files"]
    if protected_files:
        invariants.append("Do not modify protected generated files unless the Executive explicitly authorizes it.")
        restricted.extend(f"protected generated file: {path}" for path in protected_files)
    invariants.extend(clean_values(args.invariant))

    baton_scope = baton.get("scope", "") if baton else ""
    if not allowed and baton_scope:
        allowed.append(f"baton scope only: {baton_scope}")
    if role == "builder":
        restricted.append("unrelated files outside baton scope")
    elif role == "reviewer":
        restricted.append("file edits; reviewer is read-only by default")
    else:
        restricted.append("implementation edits unless explicitly taking a narrow executive patch")

    verification_level = (
        baton.get("verification_level")
        if baton
        else config["verification_policy"]["default_level"]
    )
    required_checks = clean_values(args.required_check) or verification_check_defaults(str(verification_level))

    return {
        "objective": baton.get("title", "") if baton else "Inspect and coordinate current factory state",
        "scope": baton_scope,
        "allowed_files_or_areas": unique_values(allowed),
        "restricted_files_or_areas": unique_values(restricted),
        "non_goals": unique_values(non_goals),
        "hard_invariants": unique_values(invariants),
        "required_checks": unique_values(required_checks),
    }


def recent_run_context(conn: sqlite3.Connection, run_id: str, recent: int) -> dict[str, Any]:
    batons = list(
        conn.execute(
            "SELECT * FROM batons WHERE run_id = ? ORDER BY assigned_at DESC LIMIT ?",
            (run_id, recent),
        )
    )
    events = list(
        conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (run_id, recent),
        )
    )
    return {
        "batons": [row_to_public_dict(row) for row in batons],
        "events": [row_to_public_dict(row) for row in events],
    }


def build_agent_packet(
    *,
    root: Path,
    conn: sqlite3.Connection,
    run: sqlite3.Row,
    config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    role = args.role.lower()
    if role not in AGENT_PACKET_ROLES:
        raise FactoryError(f"--role must be one of {', '.join(sorted(AGENT_PACKET_ROLES))}")
    if args.runtime_mode not in AGENT_PACKET_RUNTIME_MODES:
        raise FactoryError(f"--runtime-mode must be one of {', '.join(sorted(AGENT_PACKET_RUNTIME_MODES))}")
    if args.format not in AGENT_PACKET_FORMATS:
        raise FactoryError(f"--format must be one of {', '.join(sorted(AGENT_PACKET_FORMATS))}")
    if args.write_policy not in AGENT_PACKET_WRITE_POLICIES:
        raise FactoryError(f"--write-policy must be one of {', '.join(sorted(AGENT_PACKET_WRITE_POLICIES))}")
    if role in {"builder", "reviewer"} and not args.baton:
        raise FactoryError("--baton is required for builder and reviewer packets.")

    recent = require_limit(args.recent, field="recent")
    baton_detail: dict[str, Any] | None = None
    baton: dict[str, Any] | None = None
    if args.baton:
        baton_detail = collect_baton_detail(conn, run, args.baton, recent_events=recent)
        baton = baton_detail["baton"]

    status = collect_status(conn, root, args.db)
    prefix = command_prefix(root, args)
    acceptance_tier = baton.get("acceptance_tier") if baton else "integration"
    verification_level = (
        baton.get("verification_level")
        if baton
        else config["verification_policy"]["default_level"]
    )
    return {
        "packet_version": 1,
        "generated_at": utc_now(),
        "runtime_mode": args.runtime_mode,
        "role": role,
        "instructions": role_instructions(role),
        "project": {
            "root": str(root),
            "db": str(db_path_for(root, args.db)),
            "config": str(config_path_for(root, args.config)),
        },
        "run": row_to_public_dict(run),
        "current_status": {
            "factory_status": status["run"]["status"],
            "work_mode": status["run"]["work_mode"],
            "topology": status["run"]["topology"],
            "active_batons": status["active_batons"],
            "held_locks": status["held_locks"],
            "latest_event": status["latest_event"],
            "git": status["git"],
        },
        "baton": baton,
        "baton_evidence": baton_detail,
        "scope": packet_scope(role=role, baton=baton, config=config, args=args),
        "verification_policy": {
            "acceptance_tier": acceptance_tier,
            "verification_level": verification_level,
            "config": config["verification_policy"],
        },
        "worker_policy": worker_policy_for(role, args.write_policy),
        "handoff_schema": handoff_schema_for(role),
        "recording_commands": recording_commands_for(
            prefix=prefix,
            role=role,
            baton_id=args.baton,
            recent=recent,
        ),
        "recent_context": recent_run_context(conn, run["id"], recent),
        "completion_contract": [
            "Stay inside the packet scope and hard invariants.",
            "Run or honestly report required checks.",
            "Record CLI evidence directly only when safe and available.",
            "If CLI access is unavailable, return the handoff or review schema to the lead agent.",
            "Do not accept, commit, push, or broaden scope unless this packet explicitly gives that authority.",
        ],
    }


def markdown_bullets(values: Iterable[Any], *, empty: str) -> list[str]:
    result = [f"- {value}" for value in values if str(value).strip()]
    return result or [f"- {empty}"]


def format_agent_packet_markdown(packet: dict[str, Any]) -> str:
    role = str(packet["role"]).title()
    baton = packet.get("baton") or {}
    scope = packet["scope"]
    worker_policy = packet["worker_policy"]
    verification_policy = packet["verification_policy"]
    status = packet["current_status"]
    lines = [
        f"# Agent Packet: {role}",
        "",
        f"Generated: {packet['generated_at']}",
        f"Runtime mode: {packet['runtime_mode']}",
        f"Factory: {packet['run']['id']}",
        f"Project root: {packet['project']['root']}",
        "",
        "## Role Contract",
        "",
        f"- Role: {packet['role']}",
        f"- Instructions: {packet['instructions']}",
        f"- File write policy: {worker_policy['write_policy']}",
        f"- May run commands: {worker_policy['may_run_commands']}",
        f"- May record CLI evidence: {worker_policy['may_record_cli_evidence']}",
        "- If CLI access is unavailable, return the required evidence to the lead agent.",
        "",
        "## Current State",
        "",
        f"- Factory status: {status['factory_status']}",
        f"- Work mode: {status['work_mode']}",
        f"- Topology: {status['topology']}",
        f"- Active batons: {len(status['active_batons'])}",
        f"- Held locks: {len(status['held_locks'])}",
        f"- Git head: {status['git']['head'] or 'unavailable'}",
        "",
        "## Baton",
        "",
    ]
    if baton:
        lines.extend(
            [
                f"- ID: {baton['id']}",
                f"- Title: {baton['title']}",
                f"- Status: {baton['status']}",
                f"- Owner: {baton['owner']}",
                f"- Scope: {baton['scope'] or 'not specified'}",
                f"- Acceptance tier: {baton['acceptance_tier']}",
                f"- Verification level: {baton['verification_level']}",
            ]
        )
    else:
        lines.append("- No focused baton supplied; coordinate current factory state.")
    lines.extend(
        [
            "",
            "## Scope Controls",
            "",
            "Allowed files or areas:",
            *markdown_bullets(scope["allowed_files_or_areas"], empty="baton scope only"),
            "",
            "Restricted files or areas:",
            *markdown_bullets(scope["restricted_files_or_areas"], empty="none specified"),
            "",
            "Hard invariants:",
            *markdown_bullets(scope["hard_invariants"], empty="none specified"),
            "",
            "Non-goals:",
            *markdown_bullets(scope["non_goals"], empty="none specified"),
            "",
            "Required checks:",
            *markdown_bullets(scope["required_checks"], empty="none specified"),
            "",
            "## Verification Policy",
            "",
            f"- Acceptance tier: {verification_policy['acceptance_tier']}",
            f"- Verification level: {verification_policy['verification_level']}",
            f"- Config requires baton for verification: {verification_policy['config']['require_baton']}",
            (
                "- Config requires summary for not_run: "
                f"{verification_policy['config']['require_summary_for_not_run']}"
            ),
            "",
            "## Handoff Schema",
            "",
            "```json",
            json.dumps(packet["handoff_schema"], indent=2, sort_keys=True),
            "```",
            "",
            "## Recording Commands",
            "",
        ]
    )
    for command in packet["recording_commands"]:
        lines.extend(
            [
                f"### {command['name']}",
                "",
                f"When: {command['when']}",
                "",
                "```bash",
                command["command"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Completion Contract",
            "",
            *markdown_bullets(packet["completion_contract"], empty="none specified"),
            "",
        ]
    )
    return "\n".join(lines)


def cmd_agent_packet(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    packet = build_agent_packet(root=root, conn=conn, run=run, config=config, args=args)
    if args.format == "json":
        print_json(packet)
    else:
        print(format_agent_packet_markdown(packet))
    return 0


def agent_packet_text(packet: dict[str, Any], packet_format: str) -> str:
    if packet_format == "json":
        return json.dumps(packet, indent=2, sort_keys=True) + "\n"
    return format_agent_packet_markdown(packet)


def packet_dir_for(root: Path, raw_dir: str) -> Path:
    relative = safe_relative_path(raw_dir, field="packet_dir", label="Argument")
    return root / relative


def write_agent_packet_file(root: Path, packet: dict[str, Any], packet_format: str, packet_dir: str) -> Path:
    out_dir = packet_dir_for(root, packet_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extension = "json" if packet_format == "json" else "md"
    stamp = utc_now().replace(":", "").replace("-", "").replace("Z", "")
    baton = packet.get("baton") or {}
    filename = "-".join(
        [
            "packet",
            stamp,
            safe_slug(str(packet.get("role", "")), fallback="role"),
            safe_slug(str(baton.get("id") or "no-baton"), fallback="no-baton"),
        ]
    )
    path = out_dir / f"{filename}.{extension}"
    path.write_text(agent_packet_text(packet, packet_format), encoding="utf-8")
    return path


def has_held_baton_lock(conn: sqlite3.Connection, run_id: str, baton_id: str | None) -> bool:
    if not baton_id:
        return False
    row = conn.execute(
        """
        SELECT 1 FROM locks
        WHERE run_id = ? AND baton_id = ? AND status = 'held'
        LIMIT 1
        """,
        (run_id, baton_id),
    ).fetchone()
    return row is not None


def build_codex_spawn_command(root: Path, packet: dict[str, Any], args: argparse.Namespace) -> list[str]:
    sandbox = args.codex_sandbox
    if sandbox == "auto":
        sandbox = "workspace-write" if packet["worker_policy"]["may_edit_files"] else "read-only"
    command = [
        args.codex_bin,
        "exec",
        "--cd",
        str(root),
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        args.codex_approval,
        "--ephemeral",
    ]
    if args.codex_model:
        command.extend(["--model", args.codex_model])
    if args.codex_profile:
        command.extend(["--profile", args.codex_profile])
    if args.codex_skip_git_repo_check:
        command.append("--skip-git-repo-check")
    command.append("-")
    return command


CUSTOM_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def build_custom_spawn_command(root: Path, packet_path: Path, args: argparse.Namespace) -> list[str]:
    if not args.command.strip():
        raise FactoryError("--command is required for --adapter custom.")
    if "{packet}" not in args.command:
        raise FactoryError("Custom adapter --command must include the {packet} placeholder.")
    try:
        tokens = shlex.split(args.command)
    except ValueError as exc:
        raise FactoryError(f"Invalid custom adapter command: {exc}") from exc
    if not tokens:
        raise FactoryError("Custom adapter command must not be empty.")
    replacements = {
        "{packet}": str(packet_path),
        "{root}": str(root),
        "{role}": args.role,
        "{baton}": args.baton or "",
    }
    expanded: list[str] = []
    for token in tokens:
        for placeholder, value in replacements.items():
            token = token.replace(placeholder, value)
        unknown = CUSTOM_PLACEHOLDER_RE.search(token)
        if unknown:
            raise FactoryError(f"Unknown custom adapter placeholder: {unknown.group(0)}")
        expanded.append(token)
    return expanded


def build_spawn_command(root: Path, packet: dict[str, Any], packet_path: Path, args: argparse.Namespace) -> tuple[list[str], str | None]:
    if args.adapter == "codex-cli":
        return build_codex_spawn_command(root, packet, args), agent_packet_text(packet, args.packet_format)
    if args.adapter == "custom":
        return build_custom_spawn_command(root, packet_path, args), None
    raise FactoryError(f"--adapter must be one of {', '.join(sorted(AGENT_SPAWN_ADAPTERS))}")


def run_spawn_command(
    *,
    command: list[str],
    stdin: str | None,
    root: Path,
    timeout_seconds: int,
    output_limit: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        stdout, stdout_truncated = truncate_text(proc.stdout, output_limit)
        stderr, stderr_truncated = truncate_text(proc.stderr, output_limit)
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = truncate_text(exc.stdout if isinstance(exc.stdout, str) else "", output_limit)
        stderr, stderr_truncated = truncate_text(exc.stderr if isinstance(exc.stderr, str) else "", output_limit)
        return {
            "status": "timed_out",
            "returncode": 124,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
    except OSError as exc:
        return {
            "status": "failed",
            "returncode": 127,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout": "",
            "stderr": str(exc),
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def spawn_event_payload(
    *,
    adapter: str,
    role: str,
    baton_id: str | None,
    packet_path: Path,
    command: list[str],
    timeout_seconds: int,
    status: str | None = None,
    returncode: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "adapter": adapter,
        "role": role,
        "baton_id": baton_id or "",
        "packet_path": str(packet_path),
        "timeout_seconds": timeout_seconds,
        "command_preview": shorten(shell_join(command), 500),
    }
    if status is not None:
        payload["status"] = status
    if returncode is not None:
        payload["returncode"] = returncode
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    return payload


def cmd_agent_spawn(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    if not args.experimental and not args.dry_run:
        raise FactoryError("agent spawn is experimental; pass --experimental to execute or --dry-run to preview.")
    timeout_seconds = require_timeout(args.timeout_seconds)
    output_limit = require_output_limit(args.output_limit)
    args.format = args.packet_format
    args.runtime_mode = "adapter_spawn"

    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    packet = build_agent_packet(root=root, conn=conn, run=run, config=config, args=args)
    if packet["worker_policy"]["may_edit_files"] and args.baton and not args.allow_unlocked:
        if not has_held_baton_lock(conn, run["id"], args.baton):
            raise FactoryError("Write-capable spawn requires a held lock for --baton, or pass --allow-unlocked.")
    packet_path = write_agent_packet_file(root, packet, args.packet_format, args.packet_dir)
    command, stdin = build_spawn_command(root, packet, packet_path, args)
    result: dict[str, Any] = {
        "adapter": args.adapter,
        "role": args.role,
        "baton": args.baton,
        "packet_path": str(packet_path),
        "command": command,
        "command_preview": shell_join(command),
        "timeout_seconds": timeout_seconds,
        "experimental": args.experimental,
        "dry_run": args.dry_run,
        "events_recorded": False,
    }
    if args.dry_run:
        result.update({"status": "dry_run", "returncode": 0})
        print_json(result)
        return 0

    if not args.no_event:
        emit_event(
            conn,
            event_type="agent.spawn.started",
            actor=args.actor,
            run_id=run["id"],
            baton_id=args.baton,
            summary=f"{args.adapter} spawn started for {args.role}",
            payload=spawn_event_payload(
                adapter=args.adapter,
                role=args.role,
                baton_id=args.baton,
                packet_path=packet_path,
                command=command,
                timeout_seconds=timeout_seconds,
            ),
        )
        conn.commit()
        result["events_recorded"] = True

    execution = run_spawn_command(
        command=command,
        stdin=stdin,
        root=root,
        timeout_seconds=timeout_seconds,
        output_limit=output_limit,
    )
    result.update(execution)

    if not args.no_event:
        emit_event(
            conn,
            event_type="agent.spawn.completed",
            actor=args.actor,
            run_id=run["id"],
            baton_id=args.baton,
            summary=f"{args.adapter} spawn {execution['status']} for {args.role}",
            payload=spawn_event_payload(
                adapter=args.adapter,
                role=args.role,
                baton_id=args.baton,
                packet_path=packet_path,
                command=command,
                timeout_seconds=timeout_seconds,
                status=execution["status"],
                returncode=execution["returncode"],
                duration_ms=execution["duration_ms"],
            ),
        )
        conn.commit()

    print_json(result)
    return int(execution["returncode"])


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
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    lock_name = args.lock_name or config["default_lock_name"]
    verification_level = args.verification_level or config["verification_policy"]["default_level"]
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
            verification_level,
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
            name=lock_name,
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
            "verification_level": verification_level,
            "lock_acquired": not args.no_lock,
        },
    )
    conn.commit()
    print_json({"status": "assigned", "baton": args.baton_id, "lock": None if args.no_lock else lock_name})
    return 0


def cmd_baton_handoff(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    baton = require_baton(conn, args.baton_id)
    lock_name = args.lock_name or config["default_lock_name"]
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
        release_lock(conn, name=lock_name)
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
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    baton = require_baton(conn, args.baton_id)
    lock_name = args.lock_name or config["default_lock_name"]
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
        release_lock(conn, name=lock_name)
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
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    verification_policy = config["verification_policy"]
    if verification_policy["require_baton"] and not args.baton:
        raise FactoryError("Project config requires --baton for verification records.")
    if args.baton:
        require_baton(conn, args.baton)
    if args.result not in VERIFICATION_RESULTS:
        raise FactoryError("--result must be one of pass, fail, not_run, blocked")
    if args.duration_ms is not None and args.duration_ms < 0:
        raise FactoryError("--duration-ms must be greater than or equal to 0")
    if (
        args.result == "not_run"
        and verification_policy["require_summary_for_not_run"]
        and not args.summary.strip()
    ):
        raise FactoryError("Project config requires --summary when --result is not_run.")
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
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    lock_name = args.name or config["default_lock_name"]
    acquire_lock(
        conn,
        run_id=run["id"],
        name=lock_name,
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
        summary=f"{lock_name} acquired by {args.holder}",
        payload={"lock": lock_name},
    )
    conn.commit()
    print_json({"status": "held", "lock": lock_name, "holder": args.holder})
    return 0


def cmd_lock_release(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    run = require_run(conn)
    lock_name = args.name or config["default_lock_name"]
    release_lock(conn, name=lock_name)
    emit_event(
        conn,
        event_type="lock.released",
        actor=args.actor,
        run_id=run["id"],
        summary=f"{lock_name} released",
        payload={"lock": lock_name},
    )
    conn.commit()
    print_json({"status": "released", "lock": lock_name})
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
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    if args.recent < 1:
        raise FactoryError("--recent must be greater than 0")
    markdown = render_ledger(conn, root, args.recent, args.db)
    output_path = args.out or config["ledger_output_path"]
    if output_path:
        out = Path(output_path)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print_json({"status": "rendered", "out": str(out), "recent": args.recent})
    else:
        print(markdown)
    return 0


def doctor_check(root: Path, conn: sqlite3.Connection, config: dict[str, Any]) -> tuple[list[dict[str, str]], int]:
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

    protected_files = config["protected_generated_files"]
    for protected_file in protected_files:
        protected = root / protected_file
        check_name = f"protected_generated:{protected_file}"
        if not protected.exists():
            add("warn", check_name, "Configured protected file is missing")
            continue
        diff_code, _ = git_command(root, ["diff", "--exit-code", "--", protected_file])
        staged_code, staged = git_command(root, ["diff", "--cached", "--name-only", "--", protected_file])
        if diff_code != 0 or (staged_code == 0 and staged.strip()):
            add("fail", check_name, f"{protected_file} has diff or is staged")
        else:
            add("ok", check_name, f"{protected_file} is unchanged")

    ahead_code, ahead = git_command(root, ["status", "-sb"])
    if ahead_code == 0:
        add("ok", "branch", ahead.splitlines()[0] if ahead else "Branch status available")
    return findings, exit_code


def cmd_doctor(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    config = config_for_args(root, args)
    conn = connect(root, args.db)
    findings, exit_code = doctor_check(root, conn, config)
    if args.json:
        print_json({"status": "fail" if exit_code else "ok", "findings": findings})
    else:
        for finding in findings:
            print(f"[{finding['level']}] {finding['check']}: {finding['message']}")
    return exit_code


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=None, help="Project root; defaults to current directory.")
    parser.add_argument("--db", default=None, help="Factory DB path; defaults to .agentic-factory/factory.db.")
    parser.add_argument("--config", default=None, help="Project config path; defaults to .agentic-factory/config.json.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite-backed software factory CLI.")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    config = subparsers.add_parser("config", help="Create or show project config.")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_init = config_sub.add_parser("init", help="Create .agentic-factory/config.json.")
    config_init.add_argument("--force", action="store_true")
    config_init.set_defaults(func=cmd_config_init)
    config_show = config_sub.add_parser("show", help="Show effective project config.")
    config_show.set_defaults(func=cmd_config_show)

    init = subparsers.add_parser("init", help="Initialize a factory DB.")
    init.add_argument("--mode", default=None)
    init.add_argument("--objective", default="")
    init.add_argument("--topology", default=None)
    init.add_argument("--actor", default="Agent")
    init.add_argument("--run-id", default="")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    status = subparsers.add_parser("status", help="Show current factory state.")
    status.add_argument("--json", action="store_true")
    status.add_argument("--compact", action="store_true")
    status.set_defaults(func=cmd_status)

    agent = subparsers.add_parser("agent", help="Generate portable agent packets.")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_packet = agent_sub.add_parser("packet", help="Generate a role packet for delegation.")
    agent_packet.add_argument("--role", required=True, choices=sorted(AGENT_PACKET_ROLES))
    agent_packet.add_argument("--baton", default=None)
    agent_packet.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    agent_packet.add_argument("--format", choices=sorted(AGENT_PACKET_FORMATS), default="markdown")
    agent_packet.add_argument(
        "--runtime-mode",
        choices=sorted(AGENT_PACKET_RUNTIME_MODES),
        default="agent_cli_subagents",
    )
    agent_packet.add_argument("--write-policy", choices=sorted(AGENT_PACKET_WRITE_POLICIES), default="auto")
    agent_packet.add_argument("--allowed", action="append", default=[], help="Allowed file or area; repeat or comma-separate.")
    agent_packet.add_argument(
        "--restricted",
        action="append",
        default=[],
        help="Restricted file or area; repeat or comma-separate.",
    )
    agent_packet.add_argument("--invariant", action="append", default=[], help="Hard invariant to include.")
    agent_packet.add_argument("--required-check", action="append", default=[], help="Required check to include.")
    agent_packet.add_argument("--non-goal", action="append", default=[], help="Non-goal to include.")
    agent_packet.set_defaults(func=cmd_agent_packet)

    agent_spawn = agent_sub.add_parser("spawn", help="Experimentally spawn a packet through an adapter.")
    agent_spawn.add_argument("--adapter", required=True, choices=sorted(AGENT_SPAWN_ADAPTERS))
    agent_spawn.add_argument("--experimental", action="store_true", help="Required to execute the adapter.")
    agent_spawn.add_argument("--dry-run", action="store_true", help="Write packet and print argv without execution.")
    agent_spawn.add_argument("--role", required=True, choices=sorted(AGENT_PACKET_ROLES))
    agent_spawn.add_argument("--baton", default=None)
    agent_spawn.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    agent_spawn.add_argument("--packet-format", choices=sorted(AGENT_PACKET_FORMATS), default="markdown")
    agent_spawn.add_argument("--packet-dir", default=DEFAULT_PACKET_DIR)
    agent_spawn.add_argument(
        "--runtime-mode",
        choices=sorted(AGENT_PACKET_RUNTIME_MODES),
        default="adapter_spawn",
        help=argparse.SUPPRESS,
    )
    agent_spawn.add_argument("--write-policy", choices=sorted(AGENT_PACKET_WRITE_POLICIES), default="auto")
    agent_spawn.add_argument("--allowed", action="append", default=[], help="Allowed file or area; repeat or comma-separate.")
    agent_spawn.add_argument(
        "--restricted",
        action="append",
        default=[],
        help="Restricted file or area; repeat or comma-separate.",
    )
    agent_spawn.add_argument("--invariant", action="append", default=[], help="Hard invariant to include.")
    agent_spawn.add_argument("--required-check", action="append", default=[], help="Required check to include.")
    agent_spawn.add_argument("--non-goal", action="append", default=[], help="Non-goal to include.")
    agent_spawn.add_argument("--command", default="", help="Custom adapter command template; must include {packet}.")
    agent_spawn.add_argument("--timeout-seconds", type=int, default=DEFAULT_SPAWN_TIMEOUT_SECONDS)
    agent_spawn.add_argument("--output-limit", type=int, default=DEFAULT_SPAWN_OUTPUT_LIMIT)
    agent_spawn.add_argument("--allow-unlocked", action="store_true", help="Allow write-capable spawn without a held baton lock.")
    agent_spawn.add_argument("--no-event", action="store_true", help="Do not record agent.spawn events.")
    agent_spawn.add_argument("--actor", default="Executive")
    agent_spawn.add_argument("--codex-bin", default="codex")
    agent_spawn.add_argument("--codex-model", default="")
    agent_spawn.add_argument("--codex-profile", default="")
    agent_spawn.add_argument("--codex-sandbox", choices=sorted(CODEX_SPAWN_SANDBOXES), default="auto")
    agent_spawn.add_argument("--codex-approval", choices=sorted(CODEX_APPROVAL_POLICIES), default="never")
    agent_spawn.add_argument("--codex-skip-git-repo-check", action="store_true")
    agent_spawn.set_defaults(func=cmd_agent_spawn)

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
    baton_list = baton_sub.add_parser("list", help="List batons for the current run.")
    baton_list.add_argument("--all", action="store_true", help="Include non-active batons.")
    baton_list.add_argument("--status", action="append", default=[], help="Filter by status; repeat or comma-separate.")
    baton_list.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT)
    baton_list.add_argument("--json", action="store_true")
    baton_list.set_defaults(func=cmd_baton_list)
    baton_show = baton_sub.add_parser("show", help="Show detailed baton evidence.")
    baton_show.add_argument("baton_id")
    baton_show.add_argument("--recent-events", type=int, default=DEFAULT_LIST_LIMIT)
    baton_show.add_argument("--json", action="store_true")
    baton_show.set_defaults(func=cmd_baton_show)
    baton_create = baton_sub.add_parser("create", help="Assign a baton and acquire the writer lock.")
    baton_create.add_argument("baton_id")
    baton_create.add_argument("--title", required=True)
    baton_create.add_argument("--owner", default="Builder")
    baton_create.add_argument("--owner-thread", default="")
    baton_create.add_argument("--scope", default="")
    baton_create.add_argument("--summary", default="")
    baton_create.add_argument("--acceptance-tier", default="integration")
    baton_create.add_argument("--verification-level", default=None)
    baton_create.add_argument("--model", default="")
    baton_create.add_argument("--reasoning", default="")
    baton_create.add_argument("--actor", default="Executive")
    baton_create.add_argument("--allow-active", action="store_true")
    baton_create.add_argument("--no-lock", action="store_true")
    baton_create.add_argument("--lock-name", default=None)
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
    baton_handoff.add_argument("--lock-name", default=None)
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
    baton_accept.add_argument("--lock-name", default=None)
    baton_accept.set_defaults(func=cmd_baton_accept)

    verify = subparsers.add_parser("verify", help="Record verification commands.")
    verify_sub = verify.add_subparsers(dest="verify_command", required=True)
    verify_list = verify_sub.add_parser("list", help="List verification records.")
    verify_list.add_argument("--baton", default=None)
    verify_list.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    verify_list.add_argument("--json", action="store_true")
    verify_list.set_defaults(func=cmd_verification_list)
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
    review_list = review_sub.add_parser("list", help="List review records.")
    review_list.add_argument("--baton", default=None)
    review_list.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    review_list.add_argument("--json", action="store_true")
    review_list.set_defaults(func=cmd_review_list)
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
    lock_acquire.add_argument("--name", default=None)
    lock_acquire.add_argument("--holder", required=True)
    lock_acquire.add_argument("--baton", default=None)
    lock_acquire.add_argument("--force", action="store_true")
    lock_acquire.set_defaults(func=cmd_lock_acquire)
    lock_release = lock_sub.add_parser("release")
    lock_release.add_argument("--name", default=None)
    lock_release.add_argument("--actor", default="Agent")
    lock_release.set_defaults(func=cmd_lock_release)

    events = subparsers.add_parser("events", help="Inspect recorded events.")
    events_sub = events.add_subparsers(dest="events_command", required=True)
    events_list = events_sub.add_parser("list", help="List recent events.")
    events_list.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    events_list.add_argument("--baton", default=None)
    events_list.add_argument("--type", default="")
    events_list.add_argument("--json", action="store_true")
    events_list.set_defaults(func=cmd_events_list)

    verification = subparsers.add_parser("verification", help="Inspect verification records.")
    verification_sub = verification.add_subparsers(dest="verification_command", required=True)
    verification_list = verification_sub.add_parser("list", help="List verification records.")
    verification_list.add_argument("--baton", default=None)
    verification_list.add_argument("--recent", type=int, default=DEFAULT_LIST_LIMIT)
    verification_list.add_argument("--json", action="store_true")
    verification_list.set_defaults(func=cmd_verification_list)

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
