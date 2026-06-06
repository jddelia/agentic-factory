import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
