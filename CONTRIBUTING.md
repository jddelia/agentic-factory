# Contributing

Thanks for helping improve Agentic Factory. This repo is intentionally small:
the runtime CLI is Python stdlib-only, and tests use `unittest`.

## Local Checks

Run all local checks before opening a pull request:

```bash
bash scripts/check.sh
```

Or run them individually:

```bash
python3 scripts/validate_plugin.py .
python3 scripts/generate_cli_docs.py --check
python3 -m unittest discover -s tests -v
```

## Development Guidelines

- Keep `scripts/factory.py` runtime dependencies in the Python standard library.
- Add a schema migration for database changes instead of editing existing
  released migrations after the first public release.
- Add or update tests for CLI behavior, schema behavior, and user-visible
  output changes.
- Run `python3 scripts/generate_cli_docs.py --write` after changing CLI commands
  or argparse help.
- Keep the bundled skill self-contained. It may mention optional companion
  skills, but it must not require private local skills to be installed.
- Do not commit generated factory databases, rendered local ledgers, virtual
  environments, or cache directories.

## Pull Request Checklist

- Plugin manifest validates with `python3 scripts/validate_plugin.py .`.
- Generated CLI docs are current with `python3 scripts/generate_cli_docs.py --check`.
- Tests pass with `python3 -m unittest discover -s tests -v`.
- README or skill docs are updated for new commands or behavior.
- Backward compatibility and migration impact are described when schema changes.
