# Project Configuration

Agentic Factory can load project-local defaults from:

```text
.agentic-factory/config.json
```

Create a starter config from the target project root:

```bash
python3 /path/to/agentic-factory/scripts/factory.py config init
```

Inspect the effective config:

```bash
python3 /path/to/agentic-factory/scripts/factory.py config show
```

Use `--config <path>` before the command name to point at a different config
file. Relative config paths resolve under `--root`.

## Supported Fields

```json
{
  "default_mode": "balanced",
  "default_topology": "executive_as_ledger",
  "default_lock_name": "main-worktree",
  "ledger_output_path": "docs/build_ledger.md",
  "verification_policy": {
    "default_level": "focused",
    "require_baton": false,
    "require_summary_for_not_run": true
  },
  "protected_generated_files": []
}
```

### `default_mode`

Used by `init` when `--mode` is omitted.

### `default_topology`

Used by `init` when `--topology` is omitted.

### `default_lock_name`

Used by baton and lock commands when no lock name is provided.

Affected commands:

- `baton create`
- `baton handoff`
- `baton accept`
- `lock acquire`
- `lock release`

### `ledger_output_path`

Preferred output path for `render-ledger` when `--out` is omitted. If this is
empty or no config file exists, `render-ledger` prints markdown to stdout unless
`--out` is supplied.

The path must be relative and must stay inside the target project.

### `verification_policy.default_level`

Used by `baton create` when `--verification-level` is omitted.

### `verification_policy.require_baton`

When `true`, `verify record` requires `--baton`.

### `verification_policy.require_summary_for_not_run`

When `true`, `verify record --result not_run` requires a non-empty `--summary`.

### `protected_generated_files`

Relative paths for generated files that `doctor` should guard. For each
configured path:

- missing file: warning
- unstaged diff: failure
- staged diff: failure
- unchanged file: OK

Example:

```json
{
  "protected_generated_files": [
    "apps/web/next-env.d.ts",
    "src/generated/client.ts"
  ]
}
```

This replaces hard-coded generated-file checks with project-specific policy.

## Validation Rules

The config loader rejects:

- invalid JSON;
- top-level fields that are not documented here;
- unknown `verification_policy` fields;
- non-string string fields;
- non-boolean boolean fields;
- absolute paths;
- paths containing `..`;
- empty protected-file paths.

Config validation happens before a command uses config-driven defaults, so a
bad config fails fast instead of silently changing factory behavior.
