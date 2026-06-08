import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLI = PLUGIN_ROOT / "scripts" / "factory.py"


class FactoryCliTest(unittest.TestCase):
    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(root), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def test_baton_lifecycle_writes_structured_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                self.run_cli(root, "init", "--mode", "safe_mvp", "--objective", "Ship MVP").returncode,
                0,
            )
            create = self.run_cli(
                root,
                "baton",
                "create",
                "B-001",
                "--title",
                "Vertical slice",
                "--owner",
                "Builder",
                "--scope",
                "Build the real path",
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            self.assertIn('"status": "assigned"', create.stdout)

            status = self.run_cli(root, "status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(len(status_payload["active_batons"]), 1)
            self.assertEqual(len(status_payload["held_locks"]), 1)

            handoff = self.run_cli(
                root,
                "baton",
                "handoff",
                "B-001",
                "--summary",
                "Implemented and tested",
                "--files",
                "app.py,tests/test_app.py",
                "--verification",
                "pytest: pass",
            )
            self.assertEqual(handoff.returncode, 0, handoff.stderr)

            verify = self.run_cli(
                root,
                "verify",
                "record",
                "--baton",
                "B-001",
                "--command",
                "pytest",
                "--result",
                "pass",
                "--summary",
                "All focused tests pass",
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)

            review = self.run_cli(
                root,
                "review",
                "record",
                "--baton",
                "B-001",
                "--reviewer",
                "R-001",
                "--status",
                "accepted",
                "--summary",
                "No blocking findings",
                "--finding",
                "P2|app.py|12|resolved|Guard missing value",
            )
            self.assertEqual(review.returncode, 0, review.stderr)

            accept = self.run_cli(
                root,
                "baton",
                "accept",
                "B-001",
                "--commit",
                "abc1234",
                "--pushed-status",
                "pushed",
                "--summary",
                "Accepted",
            )
            self.assertEqual(accept.returncode, 0, accept.stderr)

            db = root / ".agentic-factory" / "factory.db"
            with sqlite3.connect(db) as conn:
                baton = conn.execute("SELECT status, commit_sha FROM batons WHERE id = 'B-001'").fetchone()
                event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                finding_count = conn.execute("SELECT COUNT(*) FROM review_findings").fetchone()[0]
            self.assertEqual(baton, ("accepted", "abc1234"))
            self.assertGreaterEqual(event_count, 5)
            self.assertEqual(finding_count, 1)

    def test_render_ledger_and_pause_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init", "--objective", "Test").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "pause", "--reason", "User review").returncode,
                0,
            )
            paused = json.loads(self.run_cli(root, "status", "--json").stdout)
            self.assertEqual(paused["run"]["status"], "paused")
            self.assertEqual(self.run_cli(root, "resume", "--reason", "Continue").returncode, 0)
            out = root / "docs" / "build_ledger.md"
            rendered = self.run_cli(root, "render-ledger", "--out", str(out))
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn("## Current Factory State", out.read_text())

    def test_single_active_baton_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "One").returncode,
                0,
            )
            second = self.run_cli(root, "baton", "create", "B-002", "--title", "Two")
            self.assertEqual(second.returncode, 2)
            self.assertIn("Active baton exists", second.stderr)

    def test_relative_custom_db_path_is_project_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init = self.run_cli(root, "--db", "state/factory.sqlite", "init")
            self.assertEqual(init.returncode, 0, init.stderr)

            status = self.run_cli(root, "--db", "state/factory.sqlite", "status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertEqual(payload["db"], str((root / "state" / "factory.sqlite").resolve()))
            self.assertTrue((root / "state" / "factory.sqlite").is_file())

    def test_unknown_baton_errors_are_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init").returncode, 0)

            verify = self.run_cli(
                root,
                "verify",
                "record",
                "--baton",
                "B-404",
                "--command",
                "pytest",
                "--result",
                "pass",
            )
            self.assertEqual(verify.returncode, 2)
            self.assertIn("Unknown baton: B-404", verify.stderr)
            self.assertNotIn("Traceback", verify.stderr)

            review = self.run_cli(root, "review", "record", "--baton", "B-404")
            self.assertEqual(review.returncode, 2)
            self.assertIn("Unknown baton: B-404", review.stderr)
            self.assertNotIn("Traceback", review.stderr)

    def test_rendered_ledger_escapes_markdown_table_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init", "--objective", "A | B").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "One | Two").returncode,
                0,
            )

            out = root / "ledger.md"
            rendered = self.run_cli(root, "render-ledger", "--out", str(out))
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            ledger = out.read_text(encoding="utf-8")
            self.assertIn("One \\| Two", ledger)
            self.assertIn("A | B", ledger)

    def test_inspection_commands_return_bounded_structured_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init", "--run-id", "inspect").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "Inspect me").returncode,
                0,
            )
            self.assertEqual(
                self.run_cli(
                    root,
                    "verify",
                    "record",
                    "--baton",
                    "B-001",
                    "--command",
                    "pytest",
                    "--result",
                    "pass",
                    "--summary",
                    "Focused pass",
                ).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli(
                    root,
                    "baton",
                    "handoff",
                    "B-001",
                    "--summary",
                    "Handed off",
                    "--files",
                    "app.py",
                ).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli(
                    root,
                    "review",
                    "record",
                    "--baton",
                    "B-001",
                    "--status",
                    "accepted",
                    "--summary",
                    "Accepted",
                    "--finding",
                    "P2|app.py|10|resolved|Document edge case",
                ).returncode,
                0,
            )
            self.assertEqual(
                self.run_cli(root, "baton", "accept", "B-001", "--commit", "abc1234").returncode,
                0,
            )

            active = json.loads(self.run_cli(root, "baton", "list", "--json").stdout)
            self.assertEqual(active["count"], 0)
            all_batons = json.loads(self.run_cli(root, "baton", "list", "--all", "--json").stdout)
            self.assertEqual(all_batons["count"], 1)
            self.assertEqual(all_batons["batons"][0]["id"], "B-001")

            shown = json.loads(self.run_cli(root, "baton", "show", "B-001", "--json").stdout)
            self.assertEqual(shown["baton"]["status"], "accepted")
            self.assertEqual(len(shown["verification"]), 1)
            self.assertEqual(len(shown["reviews"]), 1)
            self.assertEqual(shown["reviews"][0]["findings"][0]["severity"], "P2")

            events = json.loads(self.run_cli(root, "events", "list", "--recent", "3", "--json").stdout)
            self.assertEqual(events["count"], 3)
            self.assertEqual(events["events"][0]["event_type"], "baton.accepted")

            verification = json.loads(
                self.run_cli(root, "verification", "list", "--baton", "B-001", "--json").stdout
            )
            self.assertEqual(verification["count"], 1)
            self.assertEqual(verification["verification"][0]["result"], "pass")

            verify_alias = json.loads(self.run_cli(root, "verify", "list", "--baton", "B-001", "--json").stdout)
            self.assertEqual(verify_alias["count"], 1)

            reviews = json.loads(self.run_cli(root, "review", "list", "--baton", "B-001", "--json").stdout)
            self.assertEqual(reviews["count"], 1)
            self.assertEqual(reviews["reviews"][0]["findings"][0]["summary"], "Document edge case")

    def test_agent_packet_outputs_delegation_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                self.run_cli(root, "init", "--run-id", "packet", "--objective", "Packet test").returncode,
                0,
            )
            self.assertEqual(
                self.run_cli(
                    root,
                    "baton",
                    "create",
                    "B-001",
                    "--title",
                    "Packet baton",
                    "--scope",
                    "Update docs and tests only",
                    "--verification-level",
                    "focused_plus_build",
                ).returncode,
                0,
            )

            builder = self.run_cli(
                root,
                "agent",
                "packet",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--format",
                "json",
                "--allowed",
                "docs,tests",
                "--restricted",
                "secrets",
                "--invariant",
                "No network calls",
                "--required-check",
                "python3 -m unittest discover -s tests -v",
            )
            self.assertEqual(builder.returncode, 0, builder.stderr)
            packet = json.loads(builder.stdout)
            self.assertEqual(packet["packet_version"], 1)
            self.assertEqual(packet["role"], "builder")
            self.assertEqual(packet["baton"]["id"], "B-001")
            self.assertEqual(packet["baton"]["status"], "assigned")
            self.assertTrue(packet["worker_policy"]["may_edit_files"])
            self.assertEqual(packet["scope"]["allowed_files_or_areas"], ["docs", "tests"])
            self.assertIn("secrets", packet["scope"]["restricted_files_or_areas"])
            self.assertIn("No network calls", packet["scope"]["hard_invariants"])
            self.assertEqual(
                packet["scope"]["required_checks"],
                ["python3 -m unittest discover -s tests -v"],
            )
            command_text = "\n".join(command["command"] for command in packet["recording_commands"])
            self.assertIn("verify record --baton B-001", command_text)
            self.assertIn("baton handoff B-001", command_text)

            reviewer = self.run_cli(root, "agent", "packet", "--role", "reviewer", "--baton", "B-001")
            self.assertEqual(reviewer.returncode, 0, reviewer.stderr)
            self.assertIn("# Agent Packet: Reviewer", reviewer.stdout)
            self.assertIn("File write policy: read-only", reviewer.stdout)
            self.assertIn("review record --baton B-001", reviewer.stdout)

            executive = self.run_cli(root, "agent", "packet", "--role", "executive", "--recent", "2", "--format", "json")
            self.assertEqual(executive.returncode, 0, executive.stderr)
            executive_packet = json.loads(executive.stdout)
            self.assertEqual(executive_packet["role"], "executive")
            self.assertIsNone(executive_packet["baton"])
            self.assertLessEqual(len(executive_packet["recent_context"]["events"]), 2)
            self.assertIn("inspect_status", [command["name"] for command in executive_packet["recording_commands"]])

            missing_baton = self.run_cli(root, "agent", "packet", "--role", "builder")
            self.assertEqual(missing_baton.returncode, 2)
            self.assertIn("--baton is required", missing_baton.stderr)

    def test_agent_spawn_custom_adapter_is_explicit_and_records_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init", "--run-id", "spawn").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "Spawn baton").returncode,
                0,
            )
            command = (
                f"{sys.executable} -c "
                "'import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text(encoding=\"utf-8\")[:24])' "
                "{packet}"
            )

            preview = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "custom",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--command",
                command,
                "--dry-run",
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            preview_payload = json.loads(preview.stdout)
            self.assertEqual(preview_payload["status"], "dry_run")
            self.assertFalse(preview_payload["events_recorded"])
            self.assertTrue(Path(preview_payload["packet_path"]).is_file())
            self.assertIn(str(root), preview_payload["command_preview"])

            blocked = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "custom",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--command",
                command,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("pass --experimental", blocked.stderr)

            executed = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "custom",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--command",
                command,
                "--experimental",
                "--timeout-seconds",
                "10",
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            executed_payload = json.loads(executed.stdout)
            self.assertEqual(executed_payload["status"], "completed")
            self.assertEqual(executed_payload["returncode"], 0)
            self.assertTrue(executed_payload["session_id"])
            self.assertTrue(executed_payload["lifecycle_transition_recorded"])
            self.assertIn("# Agent Packet: Builder", executed_payload["stdout"])
            baton = json.loads(self.run_cli(root, "baton", "show", "B-001", "--json").stdout)
            self.assertEqual(baton["baton"]["status"], "in_progress")
            flow = json.loads(self.run_cli(root, "flow", "doctor", "--json").stdout)
            self.assertEqual(flow["status"], "ok")
            events = json.loads(
                self.run_cli(root, "events", "list", "--type", "agent.spawn.completed", "--json").stdout
            )
            self.assertEqual(events["count"], 1)
            self.assertEqual(events["events"][0]["payload"]["session_id"], executed_payload["session_id"])
            self.assertEqual(events["events"][0]["payload"]["status"], "completed")

            snapshot = json.loads(self.run_cli(root, "dashboard", "snapshot", "--recent", "10").stdout)
            self.assertTrue(snapshot["initialized"])
            self.assertEqual(snapshot["metrics"]["active_sessions"], 0)
            self.assertEqual(len(snapshot["sessions"]), 1)
            self.assertEqual(snapshot["sessions"][0]["id"], executed_payload["session_id"])
            self.assertEqual(snapshot["sessions"][0]["status"], "completed")
            self.assertIn("stdout", snapshot["sessions"][0]["metadata"])

            missing_placeholder = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "custom",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--command",
                "echo no-packet",
                "--dry-run",
            )
            self.assertEqual(missing_placeholder.returncode, 2)
            self.assertIn("{packet}", missing_placeholder.stderr)

    def test_agent_spawn_codex_cli_dry_run_and_lock_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.run_cli(root, "init", "--run-id", "codex-spawn").returncode, 0)
            adapters = json.loads(self.run_cli(root, "agent", "adapter", "list", "--json").stdout)
            self.assertIn("claude-code", [adapter["adapter"] for adapter in adapters["adapters"]])
            plan = json.loads(
                self.run_cli(
                    root,
                    "agent",
                    "permissions",
                    "plan",
                    "--adapter",
                    "custom",
                    "--profile",
                    "node-builder",
                ).stdout
            )
            self.assertEqual(plan["profile"], "node-builder")
            self.assertIn("native_permission_flags", plan["unsupported"])
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "Codex spawn").returncode,
                0,
            )
            dry_run = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "codex-cli",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--dry-run",
                "--codex-bin",
                "codex-test",
                "--permission-profile",
                "node-builder",
            )
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            payload = json.loads(dry_run.stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["command"][:2], ["codex-test", "exec"])
            self.assertIn("--sandbox", payload["command"])
            self.assertIn("workspace-write", payload["command"])
            self.assertEqual(payload["permission_profile"]["profile"], "node-builder")
            self.assertIn("sandbox", payload["permission_profile"]["enforced"])

            self.assertEqual(
                self.run_cli(
                    root,
                    "baton",
                    "handoff",
                    "B-001",
                    "--summary",
                    "Release lock",
                ).returncode,
                0,
            )
            guarded = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "custom",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--command",
                "echo {packet}",
                "--dry-run",
            )
            self.assertEqual(guarded.returncode, 2)
            self.assertIn("requires a held lock", guarded.stderr)

    def test_agent_spawn_claude_code_background_session_and_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "fake-claude-state.json"
            fake_claude = root / "fake-claude.py"
            fake_claude.write_text(
                f"""#!/usr/bin/env python3
import json
import pathlib
import sys

state = pathlib.Path({str(state)!r})
args = sys.argv[1:]
session = {{
    "sessionId": "7c5dcf5d",
    "name": "factory-builder-B-001",
    "status": "running",
    "cwd": {str(root)!r},
    "kind": "session",
    "startedAt": "2026-06-07T00:00:00Z",
}}
if "--bg" in args:
    state.write_text(json.dumps(session), encoding="utf-8")
    print("backgrounded · 7c5dcf5d · factory-builder-B-001")
    sys.exit(0)
if args and args[0] == "agents" and "--json" in args:
    payload = json.loads(state.read_text(encoding="utf-8")) if state.exists() else session
    print(json.dumps([payload]))
    sys.exit(0)
if len(args) >= 2 and args[0] == "logs":
    print("worker log for " + args[1])
    sys.exit(0)
if len(args) >= 2 and args[0] == "stop":
    payload = json.loads(state.read_text(encoding="utf-8")) if state.exists() else session
    payload["status"] = "stopped"
    state.write_text(json.dumps(payload), encoding="utf-8")
    print("stopped " + args[1])
    sys.exit(0)
print("unsupported fake claude args: " + repr(args), file=sys.stderr)
sys.exit(2)
""",
                encoding="utf-8",
            )
            fake_claude.chmod(0o755)

            self.assertEqual(self.run_cli(root, "init", "--run-id", "claude-spawn").returncode, 0)
            self.assertEqual(
                self.run_cli(root, "baton", "create", "B-001", "--title", "Claude spawn").returncode,
                0,
            )

            dry_run = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "claude-code",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--dry-run",
                "--claude-bin",
                str(fake_claude),
                "--claude-worktree",
                "--permission-profile",
                "node-builder",
            )
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            dry_payload = json.loads(dry_run.stdout)
            self.assertEqual(dry_payload["status"], "dry_run")
            self.assertIn("--bg", dry_payload["command"])
            self.assertIn("--plugin-dir", dry_payload["command"])
            self.assertIn(str(PLUGIN_ROOT), dry_payload["command"])
            self.assertIn("--worktree", dry_payload["command"])
            self.assertIn("--allowedTools", dry_payload["command"])
            self.assertEqual(dry_payload["permission_profile"]["profile"], "node-builder")

            spawned = self.run_cli(
                root,
                "agent",
                "spawn",
                "--adapter",
                "claude-code",
                "--role",
                "builder",
                "--baton",
                "B-001",
                "--experimental",
                "--claude-bin",
                str(fake_claude),
                "--timeout-seconds",
                "10",
            )
            self.assertEqual(spawned.returncode, 0, spawned.stderr)
            spawn_payload = json.loads(spawned.stdout)
            self.assertEqual(spawn_payload["status"], "running")
            self.assertEqual(spawn_payload["control_ref"], "7c5dcf5d")
            self.assertEqual(spawn_payload["session_id"], "claude-7c5dcf5d")

            session_list = self.run_cli(root, "agent", "session", "list", "--json")
            self.assertEqual(session_list.returncode, 0, session_list.stderr)
            session_payload = json.loads(session_list.stdout)
            self.assertEqual(session_payload["count"], 1)
            self.assertEqual(session_payload["sessions"][0]["control_ref"], "7c5dcf5d")
            self.assertEqual(session_payload["sessions"][0]["control_mode"], "claude_bg")
            self.assertIn("attach", session_payload["sessions"][0]["commands"])

            state.write_text(
                json.dumps(
                    {
                        "sessionId": "7c5dcf5d",
                        "name": "factory-builder-B-001",
                        "status": "waiting",
                        "waitingFor": "input needed",
                        "cwd": str(root),
                        "kind": "session",
                        "startedAt": "2026-06-07T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            snapshot = self.run_cli(root, "dashboard", "snapshot", "--recent", "10")
            self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
            snapshot_payload = json.loads(snapshot.stdout)
            self.assertEqual(snapshot_payload["sessions"][0]["status"], "waiting")
            self.assertEqual(snapshot_payload["sessions"][0]["commands"]["attach"], f"{fake_claude} attach 7c5dcf5d")

            sync = self.run_cli(root, "agent", "session", "sync", "--adapter", "claude-code")
            self.assertEqual(sync.returncode, 0, sync.stderr)
            sync_payload = json.loads(sync.stdout)
            self.assertEqual(sync_payload["updated"], 1)

            shown = self.run_cli(root, "agent", "session", "show", "claude-7c5dcf5d", "--json")
            self.assertEqual(shown.returncode, 0, shown.stderr)
            shown_payload = json.loads(shown.stdout)
            self.assertEqual(shown_payload["status"], "waiting")
            self.assertEqual(shown_payload["metadata"]["claude"]["waitingFor"], "input needed")

            logs = self.run_cli(root, "agent", "session", "logs", "claude-7c5dcf5d")
            self.assertEqual(logs.returncode, 0, logs.stderr)
            self.assertIn("worker log for 7c5dcf5d", logs.stdout)

            stopped = self.run_cli(root, "agent", "session", "stop", "claude-7c5dcf5d")
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
            stopped_payload = json.loads(stopped.stdout)
            self.assertEqual(stopped_payload["status"], "stopped")

    def test_up_bootstraps_dashboard_and_operator_control(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            up = self.run_cli(
                root,
                "up",
                "--objective",
                "Build the app",
                "--topology",
                "separate_ledger",
                "--runtime-mode",
                "agent_cli_subagents",
                "--no-open",
                "--no-serve",
            )
            self.assertEqual(up.returncode, 0, up.stderr)
            payload = json.loads(up.stdout)
            self.assertEqual(payload["status"], "initialized_no_server")
            self.assertTrue(payload["created_run"])
            self.assertTrue(payload["control_enabled"])
            self.assertFalse(payload["server_running"])
            self.assertIn("not running", payload["warning"])
            self.assertIn("?token=", payload["dashboard_url"])
            self.assertEqual(payload["primary_operator"]["role"], "Executive")
            self.assertEqual([operator["role"] for operator in payload["operators"]], ["Executive", "Ledger"])

            snapshot = json.loads(self.run_cli(root, "dashboard", "snapshot", "--recent", "20").stdout)
            self.assertEqual(snapshot["primary_operator"]["role"], "Executive")
            self.assertEqual([operator["role"] for operator in snapshot["operators"]], ["Executive", "Ledger"])
            self.assertIn("factory.bootstrap.no_server", [event["event_type"] for event in snapshot["events"]])
            no_server_event = next(event for event in snapshot["events"] if event["event_type"] == "factory.bootstrap.no_server")
            self.assertEqual(no_server_event["payload"]["primary_operator"]["role"], "Executive")
            self.assertFalse(no_server_event["payload"]["server_running"])

            create_baton = self.run_cli(
                root,
                "baton",
                "create",
                "B-001",
                "--title",
                "Dashboard wiring",
                "--owner",
                "Builder",
                "--scope",
                "Exercise dashboard baton detail and worker list",
            )
            self.assertEqual(create_baton.returncode, 0, create_baton.stderr)
            snapshot = json.loads(self.run_cli(root, "dashboard", "snapshot", "--recent", "20").stdout)
            self.assertEqual(snapshot["workers"][0]["kind"], "baton")
            self.assertEqual(snapshot["workers"][0]["baton_id"], "B-001")

            port = self.free_port()
            token = "test-token"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(CLI),
                    "--root",
                    str(root),
                    "dashboard",
                    "serve",
                    "--port",
                    str(port),
                    "--token",
                    token,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                health_payload = None
                for _ in range(30):
                    try:
                        request = urllib.request.Request(
                            f"http://127.0.0.1:{port}/api/health",
                            headers={"x-factory-token": token},
                        )
                        with urllib.request.urlopen(request, timeout=1) as response:
                            health_payload = json.loads(response.read().decode("utf-8"))
                        break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.1)
                self.assertIsNotNone(health_payload)
                self.assertTrue(health_payload["control_enabled"])

                operator_id = str(snapshot["primary_operator"]["id"])
                body = json.dumps({"actor": "Dashboard", "message": "pause until I say begin"}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/operators/{operator_id}/message",
                    data=body,
                    method="POST",
                    headers={"x-factory-token": token, "content-type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    message_payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(message_payload["status"], "recorded")
                self.assertEqual(message_payload["delivery"], "recorded_only")

                body = json.dumps({"actor": "Dashboard", "message": "please hand off the baton"}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/batons/B-001/message",
                    data=body,
                    method="POST",
                    headers={"x-factory-token": token, "content-type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    baton_message_payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(baton_message_payload["status"], "recorded")
                self.assertEqual(baton_message_payload["payload"]["baton_id"], "B-001")

                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/snapshot",
                    headers={"x-factory-token": token},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    live_snapshot = json.loads(response.read().decode("utf-8"))
                self.assertEqual(len(live_snapshot["control_messages"]), 2)
                self.assertEqual(live_snapshot["metrics"]["queued_control_messages"], 2)
            finally:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=5)

            events = json.loads(self.run_cli(root, "events", "list", "--type", "operator.message.requested", "--json").stdout)
            self.assertEqual(events["count"], 1)
            self.assertEqual(events["events"][0]["payload"]["message"], "pause until I say begin")
            baton_events = json.loads(self.run_cli(root, "events", "list", "--type", "baton.message.requested", "--json").stdout)
            self.assertEqual(baton_events["count"], 1)
            self.assertEqual(baton_events["events"][0]["payload"]["message"], "please hand off the baton")

            inbox = self.run_cli(
                root,
                "messages",
                "inbox",
                "--target-type",
                "operator",
                "--target-id",
                operator_id,
                "--claim",
                "--actor",
                "Lead Agent",
                "--json",
            )
            self.assertEqual(inbox.returncode, 0, inbox.stderr)
            inbox_payload = json.loads(inbox.stdout)
            self.assertEqual(inbox_payload["claimed"], 1)
            self.assertEqual(inbox_payload["messages"][0]["status"], "handling")
            ack = self.run_cli(
                root,
                "messages",
                "ack",
                inbox_payload["messages"][0]["public_id"],
                "--status",
                "handled",
                "--summary",
                "Handled in test",
            )
            self.assertEqual(ack.returncode, 0, ack.stderr)
            final_messages = json.loads(self.run_cli(root, "messages", "list", "--json").stdout)
            statuses = {message["message"]: message["status"] for message in final_messages["messages"]}
            self.assertEqual(statuses["pause until I say begin"], "handled")
            self.assertEqual(statuses["please hand off the baton"], "queued")

    def test_up_background_starts_dashboard_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            port = self.free_port()
            token = "background-token"
            up = self.run_cli(
                root,
                "up",
                "--objective",
                "Build the app",
                "--topology",
                "separate_ledger",
                "--runtime-mode",
                "agent_cli_subagents",
                "--port",
                str(port),
                "--token",
                token,
                "--background",
                "--no-open",
            )
            self.assertEqual(up.returncode, 0, up.stderr)
            payload = json.loads(up.stdout)
            self.assertEqual(payload["status"], "ready_for_user")
            self.assertTrue(payload["server_running"])
            self.assertIsInstance(payload["dashboard_pid"], int)
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/health",
                    headers={"x-factory-token": token},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    health_payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health_payload["status"], "ok")
                self.assertTrue(health_payload["control_enabled"])

                snapshot = json.loads(self.run_cli(root, "dashboard", "snapshot", "--recent", "20").stdout)
                self.assertIn("factory.ready_for_operations", [event["event_type"] for event in snapshot["events"]])
                ready_event = next(event for event in snapshot["events"] if event["event_type"] == "factory.ready_for_operations")
                self.assertTrue(ready_event["payload"]["server_running"])
                self.assertEqual(ready_event["payload"]["dashboard_pid"], payload["dashboard_pid"])
            finally:
                try:
                    os.kill(int(payload["dashboard_pid"]), signal.SIGTERM)
                except OSError:
                    pass

    def test_project_config_controls_defaults_and_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            subprocess.run(
                ["git", "config", "user.name", "Factory Test"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            subprocess.run(
                ["git", "config", "user.email", "factory@example.invalid"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            config_dir = root / ".agentic-factory"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps(
                    {
                        "default_mode": "strict",
                        "default_topology": "separate_ledger",
                        "default_lock_name": "custom-worktree",
                        "ledger_output_path": "factory-ledger.md",
                        "verification_policy": {
                            "default_level": "full_gate",
                            "require_baton": True,
                            "require_summary_for_not_run": True,
                        },
                        "protected_generated_files": ["generated.txt"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "generated.txt").write_text("stable\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "generated.txt"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            subprocess.run(
                ["git", "commit", "-m", "seed generated file"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(self.run_cli(root, "init", "--objective", "Config test").returncode, 0)
            status = json.loads(self.run_cli(root, "status", "--json").stdout)
            self.assertEqual(status["run"]["work_mode"], "strict")
            self.assertEqual(status["run"]["topology"], "separate_ledger")

            create = json.loads(
                self.run_cli(root, "baton", "create", "B-001", "--title", "Configured baton").stdout
            )
            self.assertEqual(create["lock"], "custom-worktree")
            with sqlite3.connect(root / ".agentic-factory" / "factory.db") as conn:
                verification_level = conn.execute(
                    "SELECT verification_level FROM batons WHERE id = 'B-001'"
                ).fetchone()[0]
            self.assertEqual(verification_level, "full_gate")

            missing_baton = self.run_cli(root, "verify", "record", "--command", "pytest", "--result", "pass")
            self.assertEqual(missing_baton.returncode, 2)
            self.assertIn("requires --baton", missing_baton.stderr)

            missing_summary = self.run_cli(
                root,
                "verify",
                "record",
                "--baton",
                "B-001",
                "--command",
                "manual check",
                "--result",
                "not_run",
            )
            self.assertEqual(missing_summary.returncode, 2)
            self.assertIn("requires --summary", missing_summary.stderr)

            rendered = self.run_cli(root, "render-ledger")
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertTrue((root / "factory-ledger.md").is_file())

            (root / "generated.txt").write_text("changed\n", encoding="utf-8")
            doctor = json.loads(self.run_cli(root, "doctor", "--json").stdout)
            self.assertEqual(doctor["status"], "fail")
            self.assertTrue(
                any(finding["check"] == "protected_generated:generated.txt" for finding in doctor["findings"])
            )

    def test_invalid_project_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".agentic-factory"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(
                json.dumps({"ledger_output_path": "../outside.md"}),
                encoding="utf-8",
            )
            result = self.run_cli(root, "config", "show")
            self.assertEqual(result.returncode, 2)
            self.assertIn("relative path inside the project", result.stderr)


if __name__ == "__main__":
    unittest.main()
