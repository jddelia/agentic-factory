# Agentic Factory

Agentic Factory is a Codex plugin for durable agentic software-factory
workflows. Its primary mode is Codex app orchestration, where a lead agent can
coordinate role-specific workers while recording durable state through a
stdlib-only Python CLI, a SQLite event store, structured baton state, review and
verification records, pause/resume checkpoints, doctor checks, and markdown
ledger rendering.

The plugin is self-contained. It ships one skill for durable CLI/state
operations and one skill for full software-factory orchestration. Earlier local
versions referenced a private `software-factory-v2` skill; this repository does
not require that skill and does not ship a conflicting copy of it.

The CLI is the factory control plane and ledger. It does not need to know how
every host runtime spawns workers. The orchestration skill chooses the best
runtime mode: Codex-native delegation when available, another agent CLI's
sub-agent mechanism when safe, serial role simulation when necessary, or manual
protocol execution for testing and debugging.

## What It Provides

- SQLite event store under `.agentic-factory/factory.db`
- Append-first factory events
- Baton assignment, handoff, acceptance, and lock commands
- Direct inspection commands for batons, events, verification, and reviews
- Agent packet generation for portable Builder, Reviewer, and Executive handoffs
- Experimental adapter spawning for packet-based external agent CLI delegation
- Optional local dashboard for agent-CLI factory-floor visibility
- Project-local config through `.agentic-factory/config.json`
- Review findings and verification records
- Pause/resume checkpoints
- Markdown build-ledger rendering
- Doctor checks for common factory drift
- A bundled CLI/state skill that tells agents how to use the tool
- A bundled orchestration skill for full factory operation

## Requirements

- Python 3.11 or newer
- No runtime Python package dependencies
- Git is optional, but enables richer `status` and `doctor` output

Optional dashboard serving requires `requirements-dashboard.txt`. Dashboard
frontend development requires Node.js 20 or newer.

## Installation Status

Until this repository is published through a Codex plugin directory or
marketplace, use it as a local plugin source and run the CLI directly from the
clone. The repo contains the plugin manifest, bundled skill, assets, scripts,
and validation checks needed for distribution.

For general Codex plugin and skill concepts, see OpenAI's
[Plugins and skills overview](https://openai.com/academy/codex-plugins-and-skills/).

Detailed docs:

- [Installation](docs/installation.md)
- [Usage](docs/usage.md)
- [Runtime modes](docs/runtime-modes.md)
- [Agent packets](docs/agent-packets.md)
- [Agent adapters](docs/agent-adapters.md)
- [Dashboard](docs/dashboard.md)
- [Project configuration](docs/configuration.md)
- [CLI reference](docs/cli.md)
- [Schema and event contract](docs/schema.md)
- [Codex-orchestrated example](examples/codex-orchestrated-session.md)
- [Manual CLI protocol transcript](examples/basic-factory/session.md)

## Quick Start

In the Codex app, start with the orchestration prompt:

```text
Run a Codex-native DB-backed software factory for this project
```

The lead agent should select runtime mode, initialize durable state, assign
batons, coordinate workers, and record evidence through the CLI.

For manual protocol testing or a direct CLI smoke check, run commands from the
target project root with the installed plugin directory:

```bash
python3 /path/to/agentic-factory/scripts/factory.py init \
  --mode safe_mvp \
  --objective "Ship the first real vertical slice"
```

Create a baton:

```bash
python3 /path/to/agentic-factory/scripts/factory.py baton create B-001 \
  --title "First vertical slice" \
  --owner "Builder" \
  --scope "Implement and verify the thin real path"
```

Inspect state:

```bash
python3 /path/to/agentic-factory/scripts/factory.py status --compact
```

Open the optional local dashboard for agent-CLI factory-floor visibility:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve --open
```

Render a human-readable ledger:

```bash
python3 /path/to/agentic-factory/scripts/factory.py render-ledger \
  --out docs/build_ledger.md
```

## Recommended Workflow

1. Use `agentic-factory-orchestration` to choose runtime mode, work mode,
   topology, acceptance tier, and verification policy.
2. Use Codex-native worker delegation when available. In other agent CLIs, use
   their native sub-agent mechanism with generated agent packets, or simulate
   roles serially.
3. Use `agentic-factory` to run `init` once per target project.
4. Run `doctor` before assigning or accepting work.
5. Use `baton create` for the active writer.
6. Use `baton handoff` to capture files, commands, verification, risks, and next
   step.
7. Use `verify record` and `review record` for evidence.
8. Use `baton accept` only after the work meets the selected acceptance tier.
9. Use `render-ledger` when humans need a markdown snapshot.
10. Use `dashboard serve` when a generic agent CLI workflow needs a visible
    local factory floor. This is additive and does not replace Codex app
    orchestration.

The database is the source of truth. The markdown ledger is a rendered view.

## Development

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run repo validation:

```bash
python3 scripts/validate_plugin.py .
```

Run both:

```bash
bash scripts/check.sh
```

## Repository Layout

```text
.codex-plugin/plugin.json     Codex plugin manifest
skills/agentic-factory/       CLI/state skill
skills/agentic-factory-orchestration/
                              Full software-factory orchestration skill
scripts/factory.py            Stdlib-only SQLite CLI
scripts/dashboard_server.py   Optional FastAPI dashboard server
scripts/generate_cli_docs.py  CLI reference generator
scripts/validate_plugin.py    Repo-local plugin hygiene validator
dashboard/                    React/Vite dashboard source and built assets
docs/                         Installation, usage, CLI, and schema docs
examples/                     End-to-end example sessions
migrations/                   SQLite schema migrations
templates/                    Handoff and review packet templates
tests/                        CLI regression tests
assets/                       Plugin icons and screenshots
```

## Design Notes

Agentic Factory uses an append-first model:

1. Commands update normalized current-state tables.
2. Every meaningful action writes an event row.
3. Markdown output is generated from durable state.

This lets agents inspect compact current state instead of repeatedly reading a
large historical ledger.

The plugin intentionally does not ship a duplicate skill named
`software-factory-v2`. Reusing that name would create avoidable conflicts for
users who already have a personal or marketplace skill installed. The public
orchestration skill is named `agentic-factory-orchestration`; it references
`agentic-factory` one-way for durable state.

The plugin also intentionally keeps direct process spawning out of the core
CLI. Host runtimes own worker creation. The orchestration skill tells the lead
agent how to preflight runtime capabilities and select the safest available
delegation mode, while `factory.py` records the resulting state transitions.

## License

MIT. See [LICENSE](LICENSE).
