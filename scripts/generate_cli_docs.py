#!/usr/bin/env python3
"""Generate or check docs/cli.md from the factory CLI help text."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "factory.py"
DOC = REPO_ROOT / "docs" / "cli.md"
COMMANDS: tuple[tuple[str, ...], ...] = (
    (),
    ("config",),
    ("config", "init"),
    ("config", "show"),
    ("init",),
    ("status",),
    ("dashboard",),
    ("dashboard", "snapshot"),
    ("dashboard", "serve"),
    ("agent",),
    ("agent", "packet"),
    ("agent", "spawn"),
    ("event",),
    ("event", "append"),
    ("baton",),
    ("baton", "list"),
    ("baton", "show"),
    ("baton", "create"),
    ("baton", "handoff"),
    ("baton", "accept"),
    ("verify",),
    ("verify", "list"),
    ("verify", "record"),
    ("review",),
    ("review", "list"),
    ("review", "record"),
    ("pause",),
    ("resume",),
    ("lock",),
    ("lock", "acquire"),
    ("lock", "release"),
    ("events",),
    ("events", "list"),
    ("verification",),
    ("verification", "list"),
    ("render-ledger",),
    ("doctor",),
)
NOTES: dict[tuple[str, ...], str] = {
    (): """
        Use global options before the command name.

        Example:

        ```bash
        python3 scripts/factory.py --root /path/to/project --db state/factory.sqlite status --json
        ```

        Common failures:

        - No command: argparse prints usage and exits non-zero.
        - Relative `--db`: resolved under `--root`, not the shell's original directory.
    """,
    ("config", "init"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py config init
        ```

        Example output shape:

        ```json
        {"status": "created", "path": ".../.agentic-factory/config.json", "config": {...}}
        ```

        Common failures:

        - Config already exists and `--force` was not supplied.
        - The target config path cannot be written.
    """,
    ("config", "show"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py config show
        ```

        Example output shape:

        ```json
        {"path": ".../.agentic-factory/config.json", "exists": true, "config": {...}}
        ```

        Common failures:

        - Config JSON is invalid.
        - Config contains unknown fields or unsafe relative paths.
    """,
    ("init",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py init --mode balanced --objective "Ship the requested outcome"
        ```

        Example output shape:

        ```json
        {"status": "initialized", "db": ".../.agentic-factory/factory.db", "run_id": "..."}
        ```

        Common failures:

        - Existing run without `--force`: returns `status: exists` without creating a new run.
        - Invalid migration filename: exits with a `factory: error:` message.
    """,
    ("status",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py status --compact
        ```

        Example output shape:

        ```text
        factory=<id> status=active mode=balanced
        active_batons=0 held_locks=0
        latest_baton=none status=none
        git=<head or unavailable>
        ```

        Common failures:

        - No run exists: initialize first with `factory.py init`.
    """,
    ("dashboard", "snapshot"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py dashboard snapshot --recent 50
        ```

        Example output shape:

        ```json
        {"initialized": true, "metrics": {"active_batons": 1}, "sessions": []}
        ```

        Common failures:

        - `--recent` is outside the allowed range.
    """,
    ("dashboard", "serve"): """
        Required arguments: none.

        The dashboard server is optional. It requires `requirements-dashboard.txt`
        and prebuilt frontend assets under `dashboard/dist`.

        Example:

        ```bash
        python3 scripts/factory.py dashboard serve --open
        ```

        Enable message-request controls explicitly:

        ```bash
        python3 scripts/factory.py dashboard serve --enable-control
        ```

        Common failures:

        - Dashboard assets are missing: run `cd dashboard && npm install && npm run build`.
        - Server dependencies are missing: install `requirements-dashboard.txt`.
        - Non-loopback host without `--allow-remote`.
        - `--port` is outside the allowed range.
    """,
    ("agent", "packet"): """
        Required arguments: `--role`.

        Builder and Reviewer packets also require `--baton`.

        Example:

        ```bash
        python3 scripts/factory.py agent packet --role builder --baton B-001
        ```

        Structured output:

        ```bash
        python3 scripts/factory.py agent packet --role reviewer --baton B-001 --format json
        ```

        Example output shape:

        ```json
        {"packet_version": 1, "role": "builder", "baton": {"id": "B-001"}, "recording_commands": []}
        ```

        Common failures:

        - No run exists.
        - Unknown baton when `--baton` is supplied.
        - `--baton` is missing for Builder or Reviewer packets.
        - `--recent` is outside the allowed range.
    """,
    ("agent", "spawn"): """
        Required arguments: `--adapter`, `--role`.

        Builder and Reviewer spawns also require `--baton`. Custom spawns require
        `--command` with a `{packet}` placeholder. Real execution requires
        `--experimental`; use `--dry-run` to preview without execution.

        Example dry run:

        ```bash
        python3 scripts/factory.py agent spawn --adapter custom --role builder --baton B-001 --command "my-agent run --prompt-file {packet}" --dry-run
        ```

        Example Codex CLI execution:

        ```bash
        python3 scripts/factory.py agent spawn --adapter codex-cli --role builder --baton B-001 --experimental
        ```

        Example output shape:

        ```json
        {"status": "completed", "adapter": "custom", "packet_path": "...", "returncode": 0}
        ```

        Common failures:

        - Missing `--experimental` for real execution.
        - Missing `{packet}` in a custom command.
        - Unknown baton or missing baton for Builder/Reviewer.
        - Write-capable spawn has no held baton lock and `--allow-unlocked` was not supplied.
        - Timeout returns status `timed_out` and exit code `124`.
        - Missing executable returns exit code `127`.
    """,
    ("event", "append"): """
        Required arguments: `--type`.

        Example:

        ```bash
        python3 scripts/factory.py event append --type factory.note --summary "Checkpoint reached"
        ```

        Example output shape:

        ```json
        {"status": "recorded", "event_type": "factory.note", "baton": null}
        ```

        Common failures:

        - No run exists.
        - `--payload` and `--payload-file` used together.
        - Payload is not a JSON object.
    """,
    ("baton", "list"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py baton list --all --json
        ```

        Example output shape:

        ```json
        {"count": 1, "batons": [{"id": "B-001", "status": "accepted"}]}
        ```

        Common failures:

        - No run exists.
        - `--limit` is less than 1 or greater than the maximum list limit.
    """,
    ("baton", "show"): """
        Required arguments: `baton_id`.

        Example:

        ```bash
        python3 scripts/factory.py baton show B-001 --json
        ```

        Example output shape:

        ```json
        {"baton": {...}, "handoffs": [], "verification": [], "reviews": [], "commits": [], "events": []}
        ```

        Common failures:

        - Unknown baton.
        - Baton does not belong to the current run.
        - `--recent-events` is outside the allowed range.
    """,
    ("baton", "create"): """
        Required arguments: `baton_id`, `--title`.

        Example:

        ```bash
        python3 scripts/factory.py baton create B-001 --title "First slice" --owner Builder
        ```

        Example output shape:

        ```json
        {"status": "assigned", "baton": "B-001", "lock": "main-worktree"}
        ```

        Common failures:

        - No run exists.
        - Another active baton exists and `--allow-active` was not supplied.
        - Writer lock is already held and `--force-lock` was not supplied.
        - Project config is invalid.
    """,
    ("baton", "handoff"): """
        Required arguments: `baton_id`, `--summary`.

        Example:

        ```bash
        python3 scripts/factory.py baton handoff B-001 --summary "Implemented" --commands "python3 -m unittest"
        ```

        Example output shape:

        ```json
        {"status": "handed_off", "baton": "B-001", "lock_released": true}
        ```

        Common failures:

        - Unknown baton.
        - No run exists.
        - Project config is invalid.
    """,
    ("baton", "accept"): """
        Required arguments: `baton_id`.

        Example:

        ```bash
        python3 scripts/factory.py baton accept B-001 --commit abc1234 --summary "Accepted"
        ```

        Example output shape:

        ```json
        {"status": "accepted", "baton": "B-001", "commit": "abc1234"}
        ```

        Common failures:

        - Unknown baton.
        - Accepting before the configured tier is satisfied is an orchestration error; the CLI records the decision you give it.
        - Project config is invalid.
    """,
    ("verify", "list"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py verify list --baton B-001 --json
        ```

        Example output shape:

        ```json
        {"count": 1, "verification": [{"result": "pass", "command": "pytest"}]}
        ```

        Common failures:

        - No run exists.
        - Unknown baton when `--baton` is supplied.
        - `--recent` is outside the allowed range.
    """,
    ("verify", "record"): """
        Required arguments: `--command`, `--result`.

        Example:

        ```bash
        python3 scripts/factory.py verify record --baton B-001 --command "python3 -m unittest" --result pass
        ```

        Example output shape:

        ```json
        {"status": "recorded", "result": "pass", "command": "python3 -m unittest"}
        ```

        Common failures:

        - `--result` is not one of `pass`, `fail`, `not_run`, or `blocked`.
        - `--duration-ms` is negative.
        - Unknown baton when `--baton` is supplied.
        - Project config requires `--baton`.
        - Project config requires `--summary` for `not_run`.
    """,
    ("review", "list"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py review list --baton B-001 --json
        ```

        Example output shape:

        ```json
        {"count": 1, "reviews": [{"status": "accepted", "findings": []}]}
        ```

        Common failures:

        - No run exists.
        - Unknown baton when `--baton` is supplied.
        - `--recent` is outside the allowed range.
    """,
    ("review", "record"): """
        Required arguments: `--baton`.

        Example:

        ```bash
        python3 scripts/factory.py review record --baton B-001 --status accepted --summary "No blockers"
        ```

        Example output shape:

        ```json
        {"status": "recorded", "review_id": 1, "findings": 0}
        ```

        Common failures:

        - Unknown baton.
        - Finding does not use `severity|file|line|status|summary`.
        - Finding line is not blank, `0`, or an integer.
    """,
    ("pause",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py pause --mode drain_to_checkpoint --reason "User review"
        ```

        Example output shape:

        ```json
        {"status": "paused", "mode": "drain_to_checkpoint", "reason": "User review"}
        ```

        Common failures:

        - No run exists.
    """,
    ("resume",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py resume --reason "User approved next baton"
        ```

        Example output shape:

        ```json
        {"status": "active", "reason": "User approved next baton"}
        ```

        Common failures:

        - No run exists.
        - Resuming unclear ownership should be handled by orchestration recovery before new baton assignment.
    """,
    ("lock", "acquire"): """
        Required arguments: `--holder`.

        Example:

        ```bash
        python3 scripts/factory.py lock acquire --holder Builder --baton B-001
        ```

        Example output shape:

        ```json
        {"status": "held", "lock": "main-worktree", "holder": "Builder"}
        ```

        Common failures:

        - Lock already held and `--force` was not supplied.
        - No run exists.
    """,
    ("lock", "release"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py lock release --name main-worktree
        ```

        Example output shape:

        ```json
        {"status": "released", "lock": "main-worktree"}
        ```

        Common failures:

        - No run exists.
        - Releasing a missing lock is idempotent at the table-update level.
        - Project config is invalid.
    """,
    ("events", "list"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py events list --recent 20 --json
        ```

        Example output shape:

        ```json
        {"count": 1, "events": [{"event_type": "factory.started"}]}
        ```

        Common failures:

        - No run exists.
        - Unknown baton when `--baton` is supplied.
        - `--recent` is outside the allowed range.
    """,
    ("verification", "list"): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py verification list --baton B-001 --json
        ```

        Example output shape:

        ```json
        {"count": 1, "verification": [{"result": "pass", "command": "pytest"}]}
        ```

        Common failures:

        - No run exists.
        - Unknown baton when `--baton` is supplied.
        - `--recent` is outside the allowed range.
    """,
    ("render-ledger",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py render-ledger --out docs/build_ledger.md --recent 20
        ```

        Example output shape:

        ```json
        {"status": "rendered", "out": ".../docs/build_ledger.md", "recent": 20}
        ```

        Common failures:

        - No run exists.
        - `--recent` is less than 1.
        - Project config has an unsafe `ledger_output_path`.
    """,
    ("doctor",): """
        Required arguments: none.

        Example:

        ```bash
        python3 scripts/factory.py doctor --json
        ```

        Example output shape:

        ```json
        {"status": "ok", "findings": [{"level": "ok", "check": "schema", "message": "..."}]}
        ```

        Common failures:

        - No run exists.
        - Failing health checks return a non-zero exit code.
    """,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs/cli.md.")
    parser.add_argument("--check", action="store_true", help="Fail if docs/cli.md is stale.")
    parser.add_argument("--write", action="store_true", help="Write docs/cli.md.")
    args = parser.parse_args()

    if args.check == args.write:
        parser.error("Use exactly one of --check or --write.")

    rendered = render_doc()
    if args.write:
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(rendered, encoding="utf-8")
        print(f"Wrote {DOC.relative_to(REPO_ROOT)}")
        return 0

    try:
        current = DOC.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"{DOC.relative_to(REPO_ROOT)} is missing; run scripts/generate_cli_docs.py --write")
        return 1
    if current != rendered:
        print(f"{DOC.relative_to(REPO_ROOT)} is stale; run scripts/generate_cli_docs.py --write")
        return 1
    print(f"{DOC.relative_to(REPO_ROOT)} is up to date")
    return 0


def render_doc() -> str:
    sections = [
        "# CLI Reference",
        "",
        "This file is generated from `scripts/factory.py --help` output.",
        "Update it with:",
        "",
        "```bash",
        "python3 scripts/generate_cli_docs.py --write",
        "```",
        "",
        "Global options apply before the command name:",
        "",
        "- `--root <path>`: target project root; defaults to the current working directory.",
        "- `--db <path>`: SQLite DB path; relative paths resolve under `--root`.",
        "- `--config <path>`: project config path; relative paths resolve under `--root`.",
        "",
        "The CLI is local-first and stdlib-only. It does not execute shell input from command arguments or spawn agent processes.",
        "",
    ]
    for command in COMMANDS:
        title = "factory.py" if not command else "factory.py " + " ".join(command)
        sections.extend(
            [
                f"## `{title}`",
                "",
                "```text",
                help_text(command),
                "```",
                "",
            ]
        )
        note = NOTES.get(command)
        if note:
            sections.extend([dedent(note).strip(), ""])
    return "\n".join(sections)


def help_text(command: tuple[str, ...]) -> str:
    env = dict(os.environ)
    env["COLUMNS"] = "100"
    proc = subprocess.run(
        [sys.executable, str(CLI), *command, "--help"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = proc.stdout if proc.returncode == 0 else proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(f"failed to get help for {command or ('root',)}: {output}")
    return normalize_help_text(output)


def normalize_help_text(output: str) -> str:
    lines: list[str] = []
    for line in output.strip().splitlines():
        if line.strip() == "..." and lines:
            lines[-1] = f"{lines[-1].rstrip()} ..."
            continue
        lines.append(line.rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
