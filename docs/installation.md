# Installation

Agentic Factory is a local-first Codex plugin package. It includes:

- `.codex-plugin/plugin.json`
- bundled skills under `skills/`
- stdlib-only CLI scripts under `scripts/`
- assets, migrations, templates, tests, and docs

## Requirements

- Python 3.11 or newer
- Git, optional but recommended
- No runtime Python package dependencies

## Local Source Use

Until the plugin is published through a plugin directory or marketplace, use the
repository clone as the plugin source and run the CLI directly:

```bash
python3 /path/to/agentic-factory/scripts/factory.py --help
```

When operating on another project, run commands from that project root:

```bash
cd /path/to/project
python3 /path/to/agentic-factory/scripts/factory.py init \
  --mode balanced \
  --objective "Build the requested outcome"
```

The default DB is created in the target project:

```text
.agentic-factory/factory.db
```

## Bundled Skills

This plugin ships two skills:

- `agentic-factory`: the narrow CLI and durable-state command contract.
- `agentic-factory-orchestration`: the full public software-factory operating
  model.

The orchestration skill references the operational skill one-way. The
operational skill does not require the orchestration skill and can be reused by
other factory doctrines.

The plugin intentionally does not ship a skill named `software-factory-v2`, so
it will not collide with private or marketplace skills using that name.

## Runtime Model

The primary runtime is the Codex app, where the orchestration skill can use
native thread or sub-agent capabilities when the host exposes them. The CLI
remains the durable state layer in every mode.

Other agent CLIs can still use the plugin by following the same baton,
handoff, review, and verification protocol with their own delegation features.
When delegation is unavailable or unsafe, one agent can run the roles serially.
Use [Agent Packets](agent-packets.md) when a non-Codex runtime needs a concrete
role prompt for Builder, Reviewer, or Executive work.
Use [Agent Adapters](agent-adapters.md) only when an experimental process-level
bridge to an external agent CLI is explicitly desired.

See [Runtime Modes](runtime-modes.md) for the full mode contract.

## Validation

From the plugin repository:

```bash
bash scripts/check.sh
```

This validates the plugin manifest and skill frontmatter, checks generated CLI
docs, and runs the CLI regression tests.

## Distribution Checklist

Before publishing:

- Run `bash scripts/check.sh`.
- Confirm `.codex-plugin/plugin.json` metadata is public and accurate.
- Confirm `README.md`, `LICENSE`, `CONTRIBUTING.md`, and `SECURITY.md` are
  present.
- Confirm generated files, DB files, caches, and local ledgers are not staged.
- Confirm the repository remote and default branch are correct.
