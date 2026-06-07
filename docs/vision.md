# Product Vision

Agentic Factory makes substantial agent-driven software work observable,
durable, and controllable without making the user manually operate the factory.

The primary experience is Codex-native orchestration: visible worker threads,
clear role boundaries, durable SQLite state, baton handoffs, review evidence,
verification records, pause/resume checkpoints, and rendered ledgers.

Generic agent CLIs are a first-class compatibility mode. They usually lack a
visible factory floor, so the plugin provides one through `factory.py up
--background` and a local dashboard backed by the same SQLite database.

## Non-Negotiable Startup

For agent CLI dashboard workflows, the agent must:

1. inspect the project and runtime capability;
2. resolve and present the startup configuration;
3. receive user confirmation;
4. run `factory.py up --background`;
5. present the dashboard URL and top-level operator;
6. pause until the user says factory operations may begin.

No baton, packet, worker spawn, file edit, or implementation command should
happen before that readiness gate. A printed dashboard URL is not enough; the
dashboard server must be running unless the action is an explicit test-only
bootstrap.

## Dashboard Direction

The dashboard is a local factory floor. It should show the top-level operator
prominently, then make batons, worker sessions, events, verification, reviews,
and ledger state easy to inspect. It records control requests honestly as
events unless a future session-backed adapter provides live delivery.

## Technical Direction

- Keep the core CLI and packaged dashboard server dependency-free in Python.
- Commit `dashboard/dist` so users do not need Node to open the dashboard.
- Keep SQLite as the durable local state contract.
- Keep reads bounded, token-gated, and loopback-first.
- Keep process adapters experimental and opt-in.
