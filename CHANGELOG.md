# Changelog

## 0.1.0

- Initial open-source preparation.
- Added split skills for CLI/state operations and public factory orchestration.
- Added installation, usage, schema, example session, and generated CLI reference docs.
- Added direct inspection commands and project-local config support.
- Clarified Codex-native runtime mode, portable agent CLI approximations, and
  manual protocol examples.
- Added agent packet generation for portable Builder, Reviewer, and Executive
  delegation contracts.
- Added experimental adapter spawning for packet-based external agent CLI
  delegation.
- Added local dashboard with React/Vite frontend, dependency-free stdlib
  serving, dashboard snapshots, event streaming, session registry visibility,
  topology-derived operator command seat, and guarded message-request controls.
- Added agent-facing `factory.py up` bootstrap for generic agent CLI factory
  floors, including readiness checkpoint, dashboard startup, and
  pause-before-operations flow.
- Strengthened skill startup gates so agent CLI factories must present setup,
  run `factory.py up`, show the dashboard/operator state, and wait for user
  readiness before batons or edits.
- Added SQLite-backed factory CLI, schema migration, templates, and tests.
