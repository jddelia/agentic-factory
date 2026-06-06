# Agentic Factory

Agentic Factory is a Codex plugin for durable agentic software-factory
workflows. It gives agents a stdlib-only Python CLI, a SQLite event store,
structured baton state, review and verification records, pause/resume
checkpoints, doctor checks, and markdown ledger rendering.

The plugin is self-contained. Earlier local versions referenced a private
`software-factory-v2` skill, but this repository now bundles the minimum
operating model inside `skills/agentic-factory/SKILL.md` so users do not need
any personal skill installed.

## What It Provides

- SQLite event store under `.agentic-factory/factory.db`
- Append-first factory events
- Baton assignment, handoff, acceptance, and lock commands
- Review findings and verification records
- Pause/resume checkpoints
- Markdown build-ledger rendering
- Doctor checks for common factory drift
- A bundled Codex skill that tells agents when and how to use the tool

## Requirements

- Python 3.11 or newer
- No runtime Python package dependencies
- Git is optional, but enables richer `status` and `doctor` output

## Installation Status

Until this repository is published through a Codex plugin directory or
marketplace, use it as a local plugin source and run the CLI directly from the
clone. The repo contains the plugin manifest, bundled skill, assets, scripts,
and validation checks needed for distribution.

For general Codex plugin and skill concepts, see OpenAI's
[Plugins and skills overview](https://openai.com/academy/codex-plugins-and-skills/).

## Quick Start

From a project root, run the CLI from the installed plugin directory:

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

Render a human-readable ledger:

```bash
python3 /path/to/agentic-factory/scripts/factory.py render-ledger \
  --out docs/build_ledger.md
```

## Recommended Workflow

1. Run `init` once per target project.
2. Run `doctor` before assigning or accepting work.
3. Use `baton create` for the active writer.
4. Use `baton handoff` to capture files, commands, verification, risks, and next
   step.
5. Use `verify record` and `review record` for evidence.
6. Use `baton accept` only after the work meets the selected acceptance tier.
7. Use `render-ledger` when humans need a markdown snapshot.

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
skills/agentic-factory/       Bundled self-contained Codex skill
scripts/factory.py            Stdlib-only SQLite CLI
scripts/validate_plugin.py    Repo-local plugin hygiene validator
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
users who already have a personal or marketplace skill installed. The bundled
`agentic-factory` skill contains the portable minimum doctrine and treats other
factory policy skills as optional companions.

## License

MIT. See [LICENSE](LICENSE).
