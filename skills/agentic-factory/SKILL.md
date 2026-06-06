---
name: agentic-factory
description: Use when operating a DB-backed agentic software factory with structured events, SQLite state, baton handoffs, reviews, verification records, pause/resume checkpoints, doctor checks, and markdown ledger rendering.
---

# Agentic Factory

Use this skill when a software build needs durable factory state, queryable
history, explicit baton ownership, structured handoffs, review records,
verification evidence, pause/resume checkpoints, or a generated build ledger.

This skill is self-contained. It can coexist with other factory policy skills,
but it must not assume they are installed. When another factory skill is
available, use that skill for richer policy and use Agentic Factory as the
durable state and command layer.

## Core Rules

- Prefer writing a structured factory event over adding prose-only history.
- Treat the SQLite database as the durable source of truth.
- Treat the markdown ledger as a rendered human-readable view.
- Keep one active writer per worktree by default.
- Do not bypass normal sandbox, approval, credential, or destructive-action
  constraints.
- Accept work only after handoff evidence and appropriate verification.

## CLI

Resolve the plugin root as the parent of this skill's `skills` directory, then
run:

```bash
python3 <plugin-root>/scripts/factory.py <command>
```

Run commands from the target project root unless a `--root` override is needed.
Default DB path:

```text
.agentic-factory/factory.db
```

## Operating Model

Choose a work mode before assigning batons. Infer it when the user's request is
clear:

- `safe_mvp`: the thinnest real vertical slice that preserves hard invariants.
- `balanced`: normal feature work with focused verification and review as risk
  requires.
- `strict`: production-grade, release-sensitive, security-sensitive, or
  high-blast-radius work.
- `release`: final hardening, release gates, deployment readiness, and blocker
  cleanup.
- `recovery`: reconcile broken, stale, colliding, or ambiguous factory state
  before new work.

Default to `balanced` when the request is ambiguous. Prefer `strict` for
production-grade open-source preparation and `safe_mvp` for narrow demo or MVP
requests.

Use these roles even when they are all embodied by one agent:

- Executive: owns scope, acceptance, ledger health, and final quality.
- Builder: owns one active implementation baton and hands off evidence.
- Reviewer: inspects handed-off work, records findings, and recommends accept,
  patch, or reject.

## First-Time Setup

Initialize the DB before the first DB-backed baton:

```bash
python3 <plugin-root>/scripts/factory.py init \
  --mode balanced \
  --objective "Build the requested project outcome"
```

Inspect compact state:

```bash
python3 <plugin-root>/scripts/factory.py status --compact
```

Run doctor before assigning or accepting work:

```bash
python3 <plugin-root>/scripts/factory.py doctor
```

## Baton Flow

Create a baton:

```bash
python3 <plugin-root>/scripts/factory.py baton create B-001 \
  --title "Thin vertical slice" \
  --owner "Builder" \
  --scope "Implement, test, and hand off the first real path" \
  --model gpt-5 \
  --reasoning high
```

Record a handoff:

```bash
python3 <plugin-root>/scripts/factory.py baton handoff B-001 \
  --owner "Builder" \
  --summary "Implemented the requested slice" \
  --files "apps/web/src/app/page.tsx" \
  --commands "pnpm test" \
  --verification "pnpm test: pass" \
  --risks "No known blocking risks" \
  --next "Executive review and acceptance"
```

Record verification:

```bash
python3 <plugin-root>/scripts/factory.py verify record \
  --baton B-001 \
  --command "pnpm test" \
  --result pass \
  --summary "All focused tests passed"
```

Record reviewer output as structured findings:

```bash
python3 <plugin-root>/scripts/factory.py review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status accepted \
  --summary "One P2 was patched" \
  --finding "P2|apps/api/src/foo.ts|42|resolved|Validate missing field before access"
```

Finding format:

```text
severity|file|line|status|summary
```

Use `line` as blank or `0` when there is no file line.

Accept a baton:

```bash
python3 <plugin-root>/scripts/factory.py baton accept B-001 \
  --commit abc1234 \
  --summary "Accepted after review and focused verification"
```

## Verification Policy

Choose a verification level that matches risk:

- `smoke`: command starts, primary workflow loads, or a narrow syntax check.
- `focused`: tests or checks directly covering the changed surface.
- `focused_plus_build`: focused checks plus package/app build.
- `full_gate`: repository's full test, lint, type, and build gate.
- `release_gate`: full gate plus release-specific checks and manual evidence.

Record skipped checks explicitly with `--result not_run` and a summary explaining
why they were not run.

## Pause And Resume

Pause the factory at a checkpoint:

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

On pause, capture active baton, dirty files, latest verification, unresolved
risks, and exact resume recommendation.

## Ledger Rendering

Generate a compact markdown ledger:

```bash
python3 <plugin-root>/scripts/factory.py render-ledger \
  --out docs/build_ledger.md \
  --recent 20
```

Do not manually parse a huge historical markdown ledger when `status`,
`doctor`, or `render-ledger` can provide the current state.

## Doctor

Run doctor checks before assigning or accepting batons:

```bash
python3 <plugin-root>/scripts/factory.py doctor
```

Doctor checks include:

- DB schema presence.
- Active baton count.
- Held writer lock count.
- Git worktree status when available.
- Protected generated-file drift for common Next.js path.
- Local branch summary when git metadata is available.

## Context Hygiene

When a factory is DB-backed, inspect in this order:

1. `factory.py status --compact`
2. current baton or handoff packet
3. latest verification and review records
4. rendered markdown ledger only if needed

Avoid reading the entire historical markdown ledger by default.
