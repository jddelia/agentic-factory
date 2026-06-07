# Agent Packets

Agent packets are portable delegation contracts generated from current factory
state. They let a lead agent hand a scoped task to a sub-agent in runtimes that
do not provide Codex-native thread orchestration, while keeping the same
durable baton, review, verification, and acceptance protocol.

The packet command does not spawn workers. It renders instructions and exact
`factory.py` recording commands for the host runtime or lead agent to use.

## Basic Flow

1. Lead agent runs orchestration preflight and `factory.py up` for generic
   agent CLI dashboard workflows.
2. Lead agent waits for the user to confirm the ready factory floor.
3. Lead agent creates or confirms a baton.
4. Lead agent generates a packet for the next role.
5. Lead agent gives the packet to a sub-agent through the host CLI's delegation
   mechanism.
6. Worker performs scoped work.
7. Worker records verification and handoff directly when CLI access is safe, or
   returns the handoff schema to the lead agent.
8. Lead agent records review and acceptance after the configured tier is met.

## Commands

Generate a Builder packet for a baton:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001
```

Generate a Reviewer packet:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role reviewer \
  --baton B-001
```

Generate an Executive packet for current state:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role executive \
  --recent 20
```

Markdown is the default. Use JSON when another tool needs structured data:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001 \
  --format json
```

## Packet Contents

Each packet includes:

- role and runtime mode;
- current factory status;
- focused baton id, title, scope, status, acceptance tier, and verification
  level when a baton is supplied;
- allowed files or areas;
- restricted files or areas;
- hard invariants;
- required checks;
- verification policy;
- worker write policy;
- role-specific handoff schema;
- exact `factory.py` command templates for recording completion;
- recent bounded context from the factory DB.

## Scope Overrides

The baton table stores durable assignment state. It intentionally does not
store every packet-time instruction. Use packet flags for delegation-specific
constraints:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001 \
  --allowed "apps/web,tests" \
  --restricted "generated,secrets" \
  --invariant "Do not make external network calls" \
  --required-check "pnpm test" \
  --non-goal "Do not redesign unrelated UI"
```

`--allowed` and `--restricted` may be repeated or comma-separated.
`--invariant`, `--required-check`, and `--non-goal` may be repeated.

## Write Policy

By default, packets use `--write-policy auto`:

- Builder packets permit scoped file edits.
- Reviewer packets are read-only.
- Executive packets are coordination-focused and read-only unless explicitly
  taking a narrow patch.

Override only when the runtime and worktree policy are clear:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role reviewer \
  --baton B-001 \
  --write-policy read-only
```

Available values are `auto`, `read-only`, and `write`.

## Runtime Mode

Packets default to `agent_cli_subagents` because they are primarily useful as a
portable bridge for non-Codex agent CLIs. You can set the runtime mode
explicitly:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent packet \
  --role builder \
  --baton B-001 \
  --runtime-mode serial_single_agent
```

Supported values match [Runtime Modes](runtime-modes.md):

- `codex_native`
- `agent_cli_subagents`
- `serial_single_agent`
- `manual_protocol`
- `adapter_spawn`

`adapter_spawn` is experimental and opt-in. The packet command still only
renders instructions; use [Agent Adapters](agent-adapters.md) for process-level
execution.

## Builder Packet Use

A Builder packet tells the worker:

- what baton to implement;
- where it may work;
- what it must not touch;
- what checks to run;
- how to record `verify record`;
- how to record `baton handoff`;
- what structured handoff to return if it cannot run the CLI.

The lead agent should inspect the returned state before routing review:

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton show B-001
```

## Reviewer Packet Use

A Reviewer packet is read-only by default. It tells the worker:

- what baton evidence to inspect;
- what scope to review;
- how to classify findings;
- how to record `review record`;
- what review schema to return if it cannot run the CLI.

The lead agent should not accept a baton until the review status and
verification evidence satisfy the configured acceptance tier.

## Executive Packet Use

An Executive packet is useful when handing coordination state to another lead
agent or when a generic CLI needs a compact state brief. It includes status,
recent batons, recent events, inspection commands, doctor commands, acceptance
templates, and ledger rendering commands.

## Safety Notes

- Packets are rendered data. They do not execute commands or spawn workers.
- Command templates are shell-quoted, but placeholders still require the worker
  or lead agent to fill in accurate evidence.
- Do not give write-capable packets to workers that share a worktree unless the
  factory lock and ownership are clear.
- Workers should record CLI evidence only when they have safe tool access.
- If worker CLI access is unavailable, the worker returns the packet schema and
  the lead agent records the DB state.
