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
  snapshot of runs, batons, sessions, events, verification, reviews, locks, and
  ledger state.
- Control layer: optional endpoints for human control actions. Control is off
  by default and must be enabled with `--enable-control`.

The UI is a React and TypeScript app built with Vite. Production assets are
served by a local FastAPI server launched from the CLI.

## Requirements

The core CLI remains stdlib-only. Dashboard serving is optional and requires:

```bash
python3 -m pip install -r requirements-dashboard.txt
```

Only dashboard contributors need Node.js:

```bash
cd dashboard
npm install
npm run build
```

The repository includes built assets under `dashboard/dist` so normal users do
not need Node just to open the dashboard.

## Start The Dashboard

From the target project root, after `factory.py init`:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve --open
```

The command prints a local URL with an access token:

```text
Agentic Factory dashboard: http://127.0.0.1:8765/?token=...
```

The token is required for API calls. Keep it local.

Enable message-request controls explicitly:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve \
  --enable-control \
  --open
```

Bind to loopback by default. To bind elsewhere, pass `--allow-remote`; a token
is still required.

## Dependency-Free Snapshot

For automation, tests, or runtimes that only need JSON:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard snapshot --recent 50
```

This command does not require FastAPI or Node.

## What The UI Shows

The first dashboard version includes:

- current run status, mode, topology, objective, DB path, and Git summary;
- active factory metrics;
- baton board grouped by status;
- agent session list and detail pane;
- packet path and adapter command preview for spawned sessions;
- bounded stdout/stderr for completed adapter sessions;
- verification and review evidence;
- recent event stream;
- markdown ledger preview.

## Agent Sessions

Real `factory.py agent spawn` executions now create rows in `agent_sessions`.
The dashboard reads those rows to show visible workers even when the underlying
runtime is a generic process.

Current process adapters record:

- session ID;
- role;
- baton ID;
- adapter;
- status;
- packet path;
- command argv;
- bounded output;
- start, last-seen, and end timestamps.

These rows are a durable registry, not a full terminal transport. Live terminal
delivery requires a future session-backed adapter such as tmux, Zellij, PTY, or
Codex-native thread integration.

## Message Controls

When the dashboard is started with `--enable-control`, the session detail pane
can record a message request for a session. For process adapters, this writes an
`agent.message.requested` event with delivery `recorded_only`.

That is intentional. The dashboard does not pretend that a completed or
noninteractive process can receive live input. Future session-backed adapters
can upgrade the same control path to live delivery.

## Security

Defaults are conservative:

- bind to `127.0.0.1`;
- generate a random access token per server start;
- disable control endpoints unless `--enable-control` is supplied;
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
