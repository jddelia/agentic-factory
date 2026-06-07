# Dashboard

The Agentic Factory dashboard is an optional local factory-floor UI for
agent-CLI and adapter-heavy workflows. The primary full-utility mode remains
Codex app orchestration. Use the dashboard when a generic runtime needs a
visible control plane for SQLite state, agent sessions, baton status, events,
verification, reviews, and ledger previews.

The dashboard is additive. It does not replace Codex-native threads, subagents,
or the orchestration skill.

## Architecture

The dashboard has two layers:

- State layer: reads the existing SQLite database and renders a bounded
  snapshot of runs, top-level operators, batons, sessions, events,
  verification, reviews, locks, and ledger state.
- Control layer: local endpoints for human control actions. Control is enabled
  by default for the dashboard use case and can be disabled with `--read-only`.

The UI is a React and TypeScript app built with Vite. Production assets are
served by a dependency-free local Python server launched from the CLI.

## Requirements

The core CLI and packaged dashboard server use only the Python standard
library. No `pip install` step is required to serve the bundled dashboard.

Only dashboard contributors need Node.js:

```bash
cd dashboard
npm install
npm run build
```

The repository includes built assets under `dashboard/dist` so normal users do
not need Node just to open the dashboard.

## Agent-Run Startup

In agent CLI workflows, the human should not have to initialize the database or
dashboard manually. The lead agent should use the orchestration skill to infer
or ask for the objective, mode, topology, and runtime policy, then run:

```bash
python3 /path/to/agentic-factory/scripts/factory.py up \
  --objective "Ship the requested project outcome" \
  --runtime-mode agent_cli_subagents \
  --background
```

`up` creates or refreshes the run, creates topology-derived operator records,
records a readiness checkpoint, starts the dashboard in the background, and
prints the values the user needs before factory work begins:

```text
Factory floor is ready.
Dashboard: http://127.0.0.1:8765/?token=...
Run: run-...
Project: /path/to/project
Topology: executive_as_ledger
Runtime mode: agent_cli_subagents
Control actions: enabled
```

The lead agent should pause at this point and ask the user to confirm that
factory operations can begin.

Use `--read-only` when the UI should observe without recording control
requests. Use `--no-serve` only for tests that intentionally do not need a
running dashboard server.

## Direct Dashboard Start

From the target project root, after `factory.py init` or `factory.py up`:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve --open
```

The command prints a local URL with an access token:

```text
Agentic Factory dashboard: http://127.0.0.1:8765/?token=...
```

The token is required for API calls. Keep it local.

When `--port` is omitted, the server starts on `8765` or the next available
nearby port. If `--port` is supplied explicitly and already in use, startup
fails instead of silently choosing another port.

Start read-only:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve \
  --read-only \
  --open
```

Bind to loopback by default. To bind elsewhere, pass `--allow-remote`; a token
is still required.

## Dependency-Free Snapshot

For automation, tests, or runtimes that only need JSON:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard snapshot --recent 50
```

This command does not require third-party Python packages or Node.

## What The UI Shows

The first dashboard version includes:

- current run status, mode, topology, objective, DB path, and Git summary;
- primary operator command seat based on topology and runtime mode;
- operator list for Executive, Ledger, Principal Partner, Lead Agent, or Solo
  Operator records;
- current factory state summary and control queue count;
- active factory metrics;
- baton board grouped by status;
- selected baton detail with scope, owner, evidence, related events, and baton
  message controls;
- derived baton workers that update from baton state even when no process
  adapter session exists;
- agent session list and detail pane;
- packet path and adapter command preview for spawned sessions;
- attach/log/stop command references for Claude Code background sessions;
- bounded stdout/stderr for completed adapter sessions;
- verification and review evidence;
- recent event stream;
- markdown ledger preview.

## Operator Command Seat

The most prominent panel is the top-level operator for the selected topology:

- `Executive` for Codex-native and executive-as-ledger factories;
- `Lead Agent` for generic agent CLI and adapter-heavy factories;
- `Principal Partner` when user-facing oversight is configured;
- `Solo Operator` for serial single-agent mode;
- `Ledger` appears as a secondary operator in separate-ledger topologies.

The command seat shows authority, status, and a message box. Messages are
durable requests recorded in the DB, not a claim that the dashboard can steer a
live terminal in every runtime.

## Agent Sessions

Real `factory.py agent spawn` executions create rows in `agent_sessions`. The
dashboard reads those rows to show visible workers even when the underlying
runtime is a generic process or external background-session supervisor.

Current session records include:

- session ID;
- role;
- baton ID;
- adapter;
- status;
- control mode and external control reference;
- packet path;
- command argv;
- bounded output;
- start, last-seen, and end timestamps.

Process adapters are a durable registry, not a full terminal transport. Claude
Code background sessions use `control_mode: claude_bg` and show attach/log/stop
commands in the detail pane. The snapshot endpoint refreshes active Claude Code
session state with bounded `claude agents --json` sync when such sessions are
present.

## Message Controls

When the dashboard is started in control mode, the operator command seat can
record `operator.message.requested` events, selected batons can record
`baton.message.requested` events, and session detail panes can record
`agent.message.requested` events. For process adapters and Claude Code
background sessions, dashboard message delivery is `recorded_only`.

That is intentional. The dashboard does not pretend that a completed or
noninteractive process can receive live input. For Claude Code background
sessions, attach to the live session through Claude's own session UI or
`claude attach <id>` when a true conversation is needed. Future transport
adapters can upgrade the same control path to direct live delivery.

The dashboard also renders a control inbox from recent message events. In
generic agent CLI workflows, the lead agent must poll or inspect those control
events during operation and respond in chat; the browser cannot force a
separate agent process to answer unless a live transport exists.

## Security

Defaults are conservative:

- bind to `127.0.0.1`;
- generate a random access token per server start;
- keep control requests local and token-gated;
- provide `--read-only` for observation-only mode;
- require `--allow-remote` for non-loopback hosts;
- serve bounded snapshots instead of unbounded event history;
- avoid arbitrary shell execution from browser requests.

The dashboard may display command output recorded by agent sessions. Treat it
as sensitive local development data.

## Contributor Workflow

Frontend development:

```bash
cd dashboard
npm install
npm run dev
```

Production build:

```bash
cd dashboard
npm run build
```

Backend smoke check:

```bash
python3 scripts/factory.py dashboard snapshot
```

Full repo check:

```bash
bash scripts/check.sh
```
