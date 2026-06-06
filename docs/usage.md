# Usage

This guide shows the normal Agentic Factory lifecycle. Use
`agentic-factory-orchestration` when deciding how to run the factory. Use
`agentic-factory` when recording or querying durable state with the CLI.

## Initialize

From the target project root:

```bash
python3 /path/to/agentic-factory/scripts/factory.py init \
  --mode balanced \
  --objective "Ship the requested project outcome"
```

Inspect state:

```bash
python3 /path/to/agentic-factory/scripts/factory.py status --compact
python3 /path/to/agentic-factory/scripts/factory.py doctor
```

Optional: create project defaults first:

```bash
python3 /path/to/agentic-factory/scripts/factory.py config init
python3 /path/to/agentic-factory/scripts/factory.py config show
```

See [Project Configuration](configuration.md) for supported fields.

## Create A Baton

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton create B-001 \
  --title "First integration slice" \
  --owner "Builder" \
  --scope "Implement, test, and hand off the first product-visible path" \
  --acceptance-tier integration \
  --verification-level focused_plus_build
```

By default, baton creation acquires the `main-worktree` lock. Use
`--allow-active` only for non-writer records or explicitly managed concurrency.

## Record Verification

```bash
python3 /path/to/agentic-factory/scripts/factory.py verify record \
  --baton B-001 \
  --command "python3 -m unittest discover -s tests -v" \
  --result pass \
  --summary "CLI regression tests passed"
```

Allowed results are `pass`, `fail`, `not_run`, and `blocked`.

## Record A Handoff

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton handoff B-001 \
  --summary "Implemented and verified the first integration slice" \
  --files "scripts/factory.py,tests/test_factory_cli.py" \
  --commands "python3 -m unittest discover -s tests -v" \
  --verification "unittest: pass" \
  --risks "No known blocking risks" \
  --next "Review and acceptance"
```

Use repeated `--files`, `--commands`, or `--verification` flags, or
comma-separated values, when recording multiple entries.

## Record Review

```bash
python3 /path/to/agentic-factory/scripts/factory.py review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status accepted \
  --summary "No blocking findings" \
  --finding "P2|scripts/factory.py|120|resolved|Clarify error message"
```

Finding format:

```text
severity|file|line|status|summary
```

## Accept

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton accept B-001 \
  --commit abc1234 \
  --pushed-status pushed \
  --summary "Accepted after review and focused verification"
```

Only accept when the selected acceptance tier is actually satisfied.

## Pause And Resume

Pause at a checkpoint:

```bash
python3 /path/to/agentic-factory/scripts/factory.py pause \
  --mode drain_to_checkpoint \
  --reason "User review"
```

Resume:

```bash
python3 /path/to/agentic-factory/scripts/factory.py resume \
  --reason "User approved next baton"
```

If ownership, dirty state, or verification evidence is unclear, switch to
recovery before assigning new work.

## Render The Ledger

```bash
python3 /path/to/agentic-factory/scripts/factory.py render-ledger \
  --out docs/build_ledger.md \
  --recent 20
```

The markdown ledger is a snapshot. Keep durable state in SQLite.

## Inspect Existing State

List batons:

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton list --all
```

Show a baton with related handoffs, verification, reviews, commits, and events:

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton show B-001
```

List recent events:

```bash
python3 /path/to/agentic-factory/scripts/factory.py events list --recent 20
```

List verification records:

```bash
python3 /path/to/agentic-factory/scripts/factory.py verification list --baton B-001
```

List review records:

```bash
python3 /path/to/agentic-factory/scripts/factory.py review list --baton B-001
```

Add `--json` to these commands when another tool or agent needs structured
output.

## Custom DB Path

Use `--db` before the command name:

```bash
python3 /path/to/agentic-factory/scripts/factory.py \
  --db state/factory.sqlite \
  status --json
```

Relative DB paths resolve under the target project root.
