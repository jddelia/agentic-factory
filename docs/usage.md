# Usage

This guide shows the durable Agentic Factory lifecycle. In the primary Codex
app mode, the Executive, Builder, Reviewer, and Ledger roles emit these CLI
commands as part of an orchestrated run. In other runtimes, a lead agent can use
the same commands with that runtime's sub-agent mechanism or simulate the roles
serially.

Use `agentic-factory-orchestration` when deciding runtime mode, work mode,
roles, review depth, and verification policy. Use `agentic-factory` when
recording or querying durable state with the CLI. See
[Runtime Modes](runtime-modes.md) for the architecture boundary.

## Runtime Selection

Before assigning a baton, choose the safest available runtime mode:

- `codex_native`: preferred. Use Codex app native thread or sub-agent
  capabilities for role-specific workers.
- `agent_cli_subagents`: use another agent CLI's delegation mechanism after
  capability preflight, usually with generated agent packets.
- `serial_single_agent`: perform roles sequentially when delegation is not
  available or not safe.
- `manual_protocol`: run commands directly for tests, examples, and debugging.

The CLI records state transitions. It does not directly spawn arbitrary worker
processes.

## Agent-CLI Factory Floor Startup

In generic agent CLI environments, the human should invoke the plugin through
the agent, not by manually running setup commands. The lead agent uses
`agentic-factory-orchestration` to resolve the objective, work mode, topology,
runtime mode, verification policy, and dashboard policy. After that setup is
clear, the lead agent runs:

```bash
python3 /path/to/agentic-factory/scripts/factory.py up \
  --objective "Ship the requested project outcome" \
  --runtime-mode agent_cli_subagents \
  --background
```

`up` initializes the DB if needed, creates topology-derived operator records,
starts the local dashboard with controls enabled by default, records
`factory.ready_for_operations`, prints the dashboard URL and run metadata, then
returns so the lead agent can pause. The lead agent should wait for the user to
confirm readiness before creating the first work baton.

Use `--read-only` for observation-only dashboards. Use `--no-serve` only for
tests that intentionally do not need a running dashboard server.

This is a required gate for agent CLI dashboard workflows. Do not create a
baton, generate packets, spawn workers, or edit project files before the agent
has presented the resolved setup, run `factory.py up --background`, shown the
dashboard URL and top-level operator, and received user confirmation to begin
operations.

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

In `codex_native` mode, the Executive normally records this baton before
delegating the scoped prompt to a Builder worker. In `agent_cli_subagents`, the
lead agent should pass the same baton scope through that CLI's delegation
mechanism. In `serial_single_agent`, keep the Builder role boundary explicit
before editing.

## Generate Agent Packets

Use packets when a runtime needs a concrete prompt for a role-specific worker.
Packets are rendered instructions; they do not spawn agents.

Builder packet:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001
```

Reviewer packet:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role reviewer \
  --baton B-001
```

Executive packet:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role executive \
  --recent 20
```

Use `--format json` when another tool needs structured packet data. See
[Agent Packets](agent-packets.md) for packet fields and runtime guidance.

## Spawn Through Experimental Adapters

Adapters are optional process-level bridges for runtimes that need to launch an
external agent CLI with a packet file. Prefer Codex-native orchestration when
available.

Preview first:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --dry-run
```

Execute only after reviewing the packet, command, lock ownership, timeout, and
workspace risk:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --experimental
```

Use [Agent Adapters](agent-adapters.md) for the full safety contract.

## Open The Dashboard

Use the local dashboard when an agent CLI workflow needs a visible factory
floor:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve --open
```

The dashboard is most useful for `agent_cli_subagents` and `adapter_spawn`
workflows where the Codex app is not the primary UI. It shows batons, sessions,
topology-derived operators, events, verification, reviews, and a ledger preview
from the same SQLite DB.

Control mode is enabled by default. Start read-only when the dashboard should
not record operator or session message requests:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve \
  --read-only \
  --open
```

For process adapters, dashboard session messages are recorded as
`agent.message.requested` events. Operator command-seat messages are recorded
as `operator.message.requested` events. Selected baton messages are recorded as
`baton.message.requested` events. They are not live terminal input unless a
future session-backed adapter provides a live transport.

In agent CLI workflows, the lead agent should inspect new dashboard control
events before creating batons, accepting work, or continuing after handoffs:

```bash
python3 /path/to/agentic-factory/scripts/factory.py events list \
  --type operator.message.requested \
  --recent 20 \
  --json
```

For automation without the web server:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard snapshot --recent 50
```

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

Workers with safe CLI access can record their own verification and handoff
evidence. Otherwise, they should return a structured handoff bundle and the
Executive or Ledger records it.

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

Reviewers are read-only by default. If the runtime cannot provide an
independent Reviewer worker, the lead agent may perform a serial review pass
and record the same review evidence.

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
