---
name: agentic-factory
description: "Use when directly recording, querying, validating, or rendering Agentic Factory SQLite state with scripts/factory.py: init, status, doctor, baton, verification, review, pause/resume, lock, event, and render-ledger commands."
---

# Agentic Factory

Use this skill as the durable state and CLI layer for DB-backed factory work.
It is intentionally narrow: it explains how to persist and query factory state,
not how to design the whole operating model.

For full factory orchestration, use `agentic-factory-orchestration`. That skill
may call into this one whenever it needs durable state.

## Contract

- Run the CLI from the target project root unless `--root` is supplied.
- Treat `.agentic-factory/factory.db` as the durable source of truth.
- Treat generated markdown ledgers as rendered views, not primary storage.
- Prefer structured CLI records over prose-only history.
- Preserve sandbox, approval, credential, and destructive-action boundaries.
- Keep one active writer lock per worktree unless the orchestrator explicitly
  configures separate worktrees.

Resolve the installed plugin root, then run commands as:

```bash
python3 <plugin-root>/scripts/factory.py <global-options> <command>
```

Global options:

- `--root <path>`: target project root; defaults to current directory.
- `--db <path>`: DB path; relative paths resolve under `--root`.
- `--config <path>`: config path; defaults to `.agentic-factory/config.json`.

## Project Config

Use project config for durable defaults:

```bash
python3 <plugin-root>/scripts/factory.py config init
python3 <plugin-root>/scripts/factory.py config show
```

Supported config fields include default mode, default topology, default lock
name, preferred ledger output path, verification policy, and protected generated
files. Invalid config fails fast before command behavior changes.

## First Touch

Before recording baton work:

```bash
python3 <plugin-root>/scripts/factory.py init \
  --mode balanced \
  --objective "Build the requested project outcome"
```

Then inspect:

```bash
python3 <plugin-root>/scripts/factory.py status --compact
python3 <plugin-root>/scripts/factory.py doctor
```

If `init` reports an existing run, inspect `status` before using `--force`.

## Baton Records

Create one active writer baton:

```bash
python3 <plugin-root>/scripts/factory.py baton create B-001 \
  --title "Implement scoped slice" \
  --owner "Builder" \
  --scope "Implement, test, and hand off the requested slice"
```

Record handoff evidence:

```bash
python3 <plugin-root>/scripts/factory.py baton handoff B-001 \
  --summary "Implemented and tested the scoped slice" \
  --files "apps/web/src/app/page.tsx" \
  --commands "pnpm test" \
  --verification "pnpm test: pass" \
  --risks "No known blocking risks" \
  --next "Review and acceptance"
```

Accept only after the orchestrator's acceptance tier is met:

```bash
python3 <plugin-root>/scripts/factory.py baton accept B-001 \
  --commit abc1234 \
  --summary "Accepted after review and focused verification"
```

## Evidence Records

Record verification:

```bash
python3 <plugin-root>/scripts/factory.py verify record \
  --baton B-001 \
  --command "pnpm test" \
  --result pass \
  --summary "Focused tests passed"
```

Use `--result not_run` with an explicit summary when a check is skipped.

Record review findings:

```bash
python3 <plugin-root>/scripts/factory.py review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status accepted \
  --summary "No blocking findings" \
  --finding "P2|apps/api/src/foo.ts|42|resolved|Validate missing field before access"
```

Finding format:

```text
severity|file|line|status|summary
```

Use blank or `0` for line when there is no file line.

## Direct Inspection

Use bounded read-only inspection commands instead of parsing the whole DB or a
large rendered ledger:

```bash
python3 <plugin-root>/scripts/factory.py baton list --all
python3 <plugin-root>/scripts/factory.py baton show B-001
python3 <plugin-root>/scripts/factory.py events list --recent 20
python3 <plugin-root>/scripts/factory.py verification list --baton B-001
python3 <plugin-root>/scripts/factory.py review list --baton B-001
```

Add `--json` when another tool needs structured output.

## Pause, Resume, And Ledger

Pause:

```bash
python3 <plugin-root>/scripts/factory.py pause \
  --mode drain_to_checkpoint \
  --reason "User review"
```

Resume:

```bash
python3 <plugin-root>/scripts/factory.py resume \
  --reason "User approved next baton"
```

Render a markdown snapshot:

```bash
python3 <plugin-root>/scripts/factory.py render-ledger \
  --out docs/build_ledger.md \
  --recent 20
```

## Inspection Order

When state exists, inspect in this order:

1. `factory.py status --compact`
2. `factory.py doctor`
3. `factory.py baton show <id>` or focused list commands
4. current handoff, verification, or review evidence
5. `factory.py render-ledger` only when a markdown snapshot is needed

Avoid reading a whole historical markdown ledger when structured status is
available.
