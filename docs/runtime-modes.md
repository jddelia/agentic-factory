# Runtime Modes

Agentic Factory is designed first for Codex app orchestration. In that mode, a
lead agent uses the bundled orchestration skill to coordinate role-specific
workers and records durable state through the bundled CLI skill.

The same factory model can run in other environments, but those environments do
not all expose the same delegation tools. The plugin therefore separates the
factory operating model from worker creation:

- `agentic-factory-orchestration` is the operating model. It chooses roles,
  runtime mode, work mode, topology, acceptance tier, verification policy, and
  recovery behavior.
- `agentic-factory` is the durable state and CLI contract. It records batons,
  handoffs, verification, reviews, locks, pauses, resumes, and rendered ledgers.
- The host runtime owns worker creation. The core CLI does not directly spawn
  arbitrary agent processes.
- Agent packets provide portable delegation prompts for runtimes that need a
  concrete sub-agent handoff contract.

## Supported Modes

### `codex_native`

Use this mode when the Codex app/runtime exposes native thread or sub-agent
tools that can run scoped worker tasks and return results to the lead agent.
This is the preferred and highest-utility mode.

Expected behavior:

- the Executive runs capability preflight and initializes factory state;
- the Executive records each baton before delegation;
- Builder and Reviewer workers receive scoped role instructions;
- workers record their own CLI evidence when they have safe tool access, or
  return structured evidence for the Executive/Ledger to record;
- the Executive accepts, commits, and renders ledgers after the selected
  acceptance tier is satisfied.

### `agent_cli_subagents`

Use this mode when another agent CLI provides its own sub-agent or delegation
mechanism. The lead agent should use that CLI's native mechanism and pass a
compact baton or review packet generated from current factory state.

This mode should still be agent-driven. The user invokes the plugin through the
agent; the orchestration skill resolves the objective, mode, topology, and
runtime policy; then the agent runs `factory.py up` to initialize the DB and
local factory floor before the first baton.

This mode is a compatibility approximation, not a guarantee that every agent
CLI behaves like Codex. Before delegation, the lead agent must determine:

- whether workers share the same worktree or run in isolated workspaces;
- whether workers can write files or must stay read-only;
- whether workers can run shell commands;
- whether workers inherit skills, plugins, credentials, or environment state;
- how the lead receives handoff output;
- how the lead cancels, pauses, or recovers stale workers.

If any of those answers are unclear and the work is risky, use
`serial_single_agent` or ask the user before launching external processes.

Packet bridge:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001
```

Optional factory-floor view:

```bash
python3 /path/to/agentic-factory/scripts/factory.py up \
  --objective "Ship the requested project outcome" \
  --runtime-mode agent_cli_subagents \
  --open
```

After `up`, the lead agent should present the dashboard URL, run ID, project
root, topology, runtime mode, control state, and top-level operator, then wait
for the user to confirm that factory operations can begin.

See [Agent Packets](agent-packets.md) for the full portable delegation flow.
See [Dashboard](dashboard.md) for local UI visibility in non-Codex runtimes.

### `serial_single_agent`

Use this mode when no reliable sub-agent mechanism exists. One agent performs
the Executive, Builder, Reviewer, and Ledger responsibilities serially. Keep the
role boundaries explicit and record the same durable CLI events.

Serial mode is valid for small or constrained tasks. It is not the preferred
mode for substantial work because review independence and concurrency are
weaker.

### `manual_protocol`

Use this mode for tests, examples, demonstrations, and human debugging. A user
or maintainer runs the CLI commands directly to exercise the same state
transitions that agents normally emit.

The manual protocol is useful for portability and regression testing, but it is
not the primary user experience.

### `adapter_spawn`

This mode is reserved for future optional adapters that may launch external
agent CLI processes. It is experimental and opt-in.

Adapters should remain opt-in because process-level spawning has additional
risks: authentication differences, sandbox mismatch, command hangs,
unstructured output, cancellation complexity, shared-worktree collisions, and
unclear credential inheritance.

Use `factory.py agent spawn --dry-run` before execution, and require
`--experimental` for real adapter runs. See [Agent Adapters](agent-adapters.md)
for the full safety contract.

Real adapter executions also create `agent_sessions` rows. The optional
dashboard reads those rows to provide a visible process/session registry for
generic agent CLI workflows.

## Capability Preflight

Before assigning worker batons, the Executive should inspect the runtime and
record or summarize:

- selected `runtime_mode`;
- available native thread or sub-agent tools;
- worker workspace model: shared worktree, isolated worktree, forked workspace,
  or unknown;
- worker write capability;
- worker shell capability;
- worker skill/plugin inheritance;
- credential and secret inheritance;
- lead visibility into worker output;
- cancellation, timeout, pause, and resume behavior;
- known limits for prompt size, context, tool calls, and long-running commands.

The lead should not run arbitrary external agent processes just to discover
capabilities. Prefer known runtime metadata, available tool descriptions, or a
safe read-only preflight.

## Delegation Discipline

All modes follow the same durable state discipline:

1. Inspect status and run `doctor`.
2. Create or confirm the baton before assigning work.
3. Give each worker explicit scope, non-goals, allowed areas, restricted areas,
   required checks, and handoff requirements. Use `agent packet` when the host
   runtime needs a portable sub-agent prompt.
4. Preserve one active writer per worktree unless separate worktrees and merge
   policy are configured.
5. Record verification and handoff evidence before review.
6. Record review findings before acceptance.
7. Accept and commit only after the selected tier is satisfied.
8. Render markdown ledgers only as snapshots; the SQLite DB remains the source
   of truth.

## Choosing A Mode

Prefer modes in this order:

1. `codex_native` for full Codex app utility.
2. `agent_cli_subagents` when the host CLI has clear, safe delegation support.
3. `serial_single_agent` when delegation is unavailable or ambiguous.
4. `manual_protocol` for tests, examples, and debugging.
5. `adapter_spawn` only for explicit experimental adapters.
