---
name: agentic-factory
description: "Use when directly bootstrapping, recording, querying, validating, rendering, generating portable packets, opening the local dashboard, or using session/process adapters from Agentic Factory SQLite state with scripts/factory.py: up, init, status, doctor, dashboard, baton, agent packet, agent spawn, agent session, verification, review, pause/resume, lock, event, and render-ledger commands."
---

# Agentic Factory

Use this skill as the durable state and CLI layer for DB-backed factory work.
It is intentionally narrow: it explains how to persist and query factory state,
not how to design the whole operating model.

For full factory orchestration, use `agentic-factory-orchestration`. That skill
may call into this one whenever it needs durable state.

This skill does not spawn agents or choose worker topology. In Codex-native
factory runs, the orchestration skill uses host delegation capabilities and this
skill records the resulting state transitions. In other runtimes, the lead
agent may use an agent CLI's own sub-agent mechanism, generated agent packets,
session/process adapters, or serial role simulation while using the same
records.
The local dashboard can provide factory-floor visibility for those non-Codex
or adapter-heavy workflows.

## Build Request Gate

If the user asks to build, implement, run, or operate a full factory, do not
start with baton commands just because the objective is clear. First use
`agentic-factory-orchestration` and follow its Required Sequence.

For generic agent CLI runtimes, that means:

1. the orchestration skill resolves and presents the startup configuration;
2. the user confirms the setup;
3. the agent runs `factory.py up --background`;
4. the agent presents the dashboard URL and top-level operator;
5. the agent pauses until the user says factory operations may begin.

Only after that readiness gate should this CLI/state skill be used for
`status`, `doctor`, `baton create`, packets, handoffs, verification, review, or
acceptance. Direct use of the command examples below is appropriate for
manual protocol testing, state inspection, recovery, or explicit state-only
requests.

## Contract

- Run the CLI from the target project root unless `--root` is supplied.
- Treat `.agentic-factory/factory.db` as the durable source of truth.
- Treat generated markdown ledgers as rendered views, not primary storage.
- Prefer structured CLI records over prose-only history.
- Preserve sandbox, approval, credential, and destructive-action boundaries.
- Keep one active writer lock per worktree unless the orchestrator explicitly
  configures separate worktrees.
- Treat worker creation as host-runtime behavior, not a `factory.py`
  responsibility.

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

For agent CLI dashboard workflows, prefer the agent-facing bootstrap after the
orchestration skill has resolved objective, mode, topology, and runtime policy:

```bash
python3 <plugin-root>/scripts/factory.py up \
  --objective "Build the requested outcome" \
  --runtime-mode agent_cli_subagents \
  --background
```

`up --background` initializes or refreshes the run, creates topology-derived
operator records, starts the local dashboard with controls enabled by default,
records a readiness checkpoint, prints the dashboard URL/run/topology/runtime
values as JSON, and returns so the lead agent can pause for user confirmation
before factory operations begin.

Use `--read-only` when the dashboard should not record control requests. Use
`--no-serve` only for tests that intentionally do not need a running dashboard
server.

For Codex-native or manual state-only startup:

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
python3 <plugin-root>/scripts/factory.py dashboard snapshot --recent 50
```

Add `--json` when another tool needs structured output.

## Dashboard Control Messages

Dashboard messages are recorded as events. They do not automatically interrupt
or steer an agent unless the lead agent reads them. In agent-CLI dashboard
workflows, inspect these queues before material state transitions:

```bash
python3 <plugin-root>/scripts/factory.py events list --type operator.message.requested --recent 20 --json
python3 <plugin-root>/scripts/factory.py events list --type baton.message.requested --recent 20 --json
python3 <plugin-root>/scripts/factory.py events list --type agent.message.requested --recent 20 --json
```

Respond to new control events in chat and record any resulting pause, baton,
handoff, review, or acceptance change before continuing.

## Local Dashboard

Use the dashboard when a generic agent CLI or adapter workflow needs a visible
factory floor:

```bash
python3 <plugin-root>/scripts/factory.py dashboard serve --open
```

The packaged dashboard server has no third-party Python dependencies. Control
mode is enabled by default. Start it read-only when dashboard message requests
should be disabled:

```bash
python3 <plugin-root>/scripts/factory.py dashboard serve --read-only --open
```

Operator command-seat messages are recorded as `operator.message.requested`
events. For process adapters, session messages are recorded as
`agent.message.requested` events. They are not live terminal input unless a
session-backed adapter provides live delivery.

## Agent Packets

Generate portable role packets when a non-Codex runtime, a serial role pass, or
a handoff to another lead needs a concrete prompt derived from current state:

```bash
python3 <plugin-root>/scripts/factory.py agent packet \
  --role builder \
  --baton B-001

python3 <plugin-root>/scripts/factory.py agent packet \
  --role reviewer \
  --baton B-001

python3 <plugin-root>/scripts/factory.py agent packet \
  --role executive \
  --recent 20
```

Use `--format json` when another tool needs structured packet data. Packets are
rendered instructions and command templates; they do not spawn workers.

## Experimental Adapters

Use adapters only when the host runtime cannot provide safer native delegation
and the user or project explicitly wants a session/process bridge. Prefer
first-class session-backed adapters over generic process commands when
available.

For Claude Code CLI background sessions:

```bash
python3 <plugin-root>/scripts/factory.py agent spawn \
  --adapter claude-code \
  --role builder \
  --baton B-001 \
  --experimental
```

Then refresh, inspect, log, or stop the live session:

```bash
python3 <plugin-root>/scripts/factory.py agent session list --sync --json
python3 <plugin-root>/scripts/factory.py agent session show claude-<id> --json
python3 <plugin-root>/scripts/factory.py agent session logs claude-<id>
python3 <plugin-root>/scripts/factory.py agent session stop claude-<id>
```

Use `--claude-worktree` only when isolated write worktrees and merge handling
are intentional.

For custom process commands, always dry-run first:

```bash
python3 <plugin-root>/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --dry-run
```

Execute only after checking the packet, command, lock ownership, timeout, and
workspace risk:

```bash
python3 <plugin-root>/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --experimental
```

For the Codex CLI adapter:

```bash
python3 <plugin-root>/scripts/factory.py agent spawn \
  --adapter codex-cli \
  --role builder \
  --baton B-001 \
  --experimental
```

Adapters write packet files under `.agentic-factory/packets/`, run without
`shell=True`, enforce bounded launch/process timeouts, capture bounded output,
and record `agent_sessions` rows plus spawn/session events for real executions
unless `--no-event` is supplied.

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
