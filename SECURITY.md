# Security Policy

Agentic Factory stores local project workflow state in SQLite under the target
project's `.agentic-factory/` directory by default. That state can include file
paths, command names, summaries, review notes, and other metadata that agents or
users record.

## Reporting Vulnerabilities

Please report security issues privately through GitHub Security Advisories for
the repository once they are enabled. If advisories are not available yet, open a
minimal public issue that asks for a private contact path and does not include
exploit details.

## Scope

Security-relevant issues include:

- Unsafe path handling that can write outside the requested project or DB path.
- SQL migration or query behavior that corrupts factory state.
- Commands that unexpectedly execute shell input.
- Documentation that encourages bypassing sandbox, approval, credential, or
  destructive-action safeguards.

The CLI is intended to remain Python stdlib-only and local-first. It should not
phone home or require network access for normal operation.
