# Basic Factory Session

This example walks through a realistic Agentic Factory run in a separate target
project. It demonstrates the normal lifecycle:

1. initialize
2. create baton
3. record verification
4. hand off
5. record review
6. accept
7. render ledger

The commands use `PLUGIN_ROOT` so the target project does not need to live
inside this plugin repository.

## Setup

```bash
export PLUGIN_ROOT=/path/to/agentic-factory
mkdir -p /tmp/agentic-factory-basic-demo
cd /tmp/agentic-factory-basic-demo
git init
git config user.name "Example Maintainer"
git config user.email "maintainer@example.invalid"
```

Create a tiny project file so the baton has a concrete scope:

```bash
cat > hello.py <<'PY'
def greeting(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greeting("Factory"))
PY
```

## 1. Initialize

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" init \
  --run-id basic-demo \
  --mode balanced \
  --objective "Add a tested greeting helper"
```

Example output:

```json
{
  "db": "/tmp/agentic-factory-basic-demo/.agentic-factory/factory.db",
  "run_id": "basic-demo",
  "status": "initialized"
}
```

Inspect compact state:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" status --compact
```

Example output:

```text
factory=basic-demo status=active mode=balanced
active_batons=0 held_locks=0
latest_baton=none status=none
git=unavailable
```

## 2. Create Baton

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton create B-001 \
  --title "Add greeting helper coverage" \
  --owner "Builder" \
  --scope "Add focused coverage for hello.greeting" \
  --acceptance-tier integration \
  --verification-level focused
```

Example output:

```json
{
  "baton": "B-001",
  "lock": "main-worktree",
  "status": "assigned"
}
```

## 3. Record Verification

Create a focused test:

```bash
mkdir -p tests
cat > tests/test_hello.py <<'PY'
import unittest

from hello import greeting


class GreetingTest(unittest.TestCase):
    def test_greeting_uses_name(self) -> None:
        self.assertEqual(greeting("Factory"), "Hello, Factory!")


if __name__ == "__main__":
    unittest.main()
PY
```

Run and record verification:

```bash
python3 -m unittest discover -s tests -v

python3 "$PLUGIN_ROOT/scripts/factory.py" verify record \
  --baton B-001 \
  --command "python3 -m unittest discover -s tests -v" \
  --result pass \
  --summary "Focused greeting test passed"
```

Example output:

```json
{
  "command": "python3 -m unittest discover -s tests -v",
  "result": "pass",
  "status": "recorded"
}
```

## 4. Handoff

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton handoff B-001 \
  --summary "Added focused greeting helper coverage" \
  --files "hello.py,tests/test_hello.py" \
  --commands "python3 -m unittest discover -s tests -v" \
  --verification "unittest: pass" \
  --risks "No known blocking risks" \
  --next "Reviewer should inspect the focused test and recommend acceptance"
```

Example output:

```json
{
  "baton": "B-001",
  "lock_released": true,
  "status": "handed_off"
}
```

## 5. Review

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status accepted \
  --summary "Focused test covers the helper behavior and no blocking issues were found"
```

Example output:

```json
{
  "findings": 0,
  "review_id": 1,
  "status": "recorded"
}
```

With findings, use:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status patch_required \
  --summary "One issue needs a narrow patch" \
  --finding "P2|tests/test_hello.py|8|open|Add an assertion for punctuation"
```

## 6. Accept

Commit the accepted files in the target project:

```bash
git add hello.py tests/test_hello.py
git commit -m "test: add greeting helper coverage"
COMMIT_SHA="$(git rev-parse --short HEAD)"
```

Record acceptance:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton accept B-001 \
  --commit "$COMMIT_SHA" \
  --pushed-status local_only \
  --summary "Accepted after focused verification and review"
```

Example output:

```json
{
  "baton": "B-001",
  "commit": "abc1234",
  "status": "accepted"
}
```

## 7. Render Ledger

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" render-ledger \
  --out docs/build_ledger.md \
  --recent 20
```

Example output:

```json
{
  "out": "/tmp/agentic-factory-basic-demo/docs/build_ledger.md",
  "recent": 20,
  "status": "rendered"
}
```

The rendered ledger contains the current state, recent batons, and recent
events. Example excerpt:

~~~markdown
# Build Ledger

## Current Factory State

```text
Factory status: active
Project root: /tmp/agentic-factory-basic-demo
Operating mode: balanced
Topology: executive_as_ledger
Objective: Add a tested greeting helper
Active batons: 0
Held locks: 0
Git head: abc1234 test: add greeting helper coverage
```

## Recent Batons

| Baton | Status | Title | Commit | Updated |
| --- | --- | --- | --- | --- |
| B-001 | accepted | Add greeting helper coverage | abc1234 | ... |

## Recent Events

| Time | Type | Baton | Summary |
| --- | --- | --- | --- |
| ... | baton.accepted | B-001 | Accepted after focused verification and review |
~~~

## Inspect The SQLite State

The generated DB is local workflow state and should not be committed:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton list --all
python3 "$PLUGIN_ROOT/scripts/factory.py" baton show B-001
python3 "$PLUGIN_ROOT/scripts/factory.py" events list --recent 20
python3 "$PLUGIN_ROOT/scripts/factory.py" verification list --baton B-001
python3 "$PLUGIN_ROOT/scripts/factory.py" review list --baton B-001
```

You can also inspect the raw tables directly:

```bash
sqlite3 .agentic-factory/factory.db ".tables"
sqlite3 .agentic-factory/factory.db "select event_type, baton_id, summary from events order by id;"
```

Expected event sequence:

```text
factory.started
baton.assigned
verification.completed
baton.handed_off
review.recorded
baton.accepted
```
