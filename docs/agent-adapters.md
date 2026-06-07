# Agent Adapters

Agent adapters are an experimental, opt-in bridge from Agentic Factory packets
to external agent CLI processes. They are useful when a runtime does not provide
Codex-native thread orchestration but can run a separate agent process from the
shell.

Adapters are not the primary runtime model. Prefer Codex-native orchestration
when available. Use adapters only when the workspace, credentials, sandbox,
timeouts, and recovery behavior are understood.

## Safety Model

`factory.py agent spawn`:

- generates the same packet as `factory.py agent packet`;
- writes the packet under `.agentic-factory/packets/` by default;
- builds adapter argv without `shell=True`;
- expands only documented placeholders for custom commands;
- requires `--experimental` for real execution;
- supports `--dry-run` for preview;
- enforces a timeout;
- captures bounded stdout and stderr;
- creates an `agent_sessions` row for real executions;
- records `agent.spawn.started` and `agent.spawn.completed` events for real
  executions unless `--no-event` is supplied.

The command does not create a native Codex app thread. It launches a local
process.

## Dry Run First

Always preview the adapter command before execution:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --dry-run
```

The dry-run writes the packet file and prints the argv that would be executed.
It does not run the adapter and does not record spawn events.

## Custom Adapter

Use `custom` for any agent CLI that accepts a prompt file:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter custom \
  --role builder \
  --baton B-001 \
  --command "my-agent run --prompt-file {packet}" \
  --experimental
```

The command template is parsed with `shlex.split` and executed with
`subprocess.run(..., shell=False)`.

Supported placeholders:

- `{packet}`: generated packet path.
- `{root}`: target project root.
- `{role}`: packet role.
- `{baton}`: baton id, or empty for Executive packets.

Unknown placeholders fail fast. `{packet}` is required so the spawned process
receives the delegation contract.

## Codex CLI Adapter

Use `codex-cli` when the local `codex` command is installed and authenticated:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter codex-cli \
  --role builder \
  --baton B-001 \
  --experimental
```

The adapter runs `codex exec` non-interactively, passes the packet on stdin,
sets `--cd` to the project root, uses `--ask-for-approval never`, and runs
ephemerally by default. Sandbox defaults are derived from the packet:

- Builder packets use `workspace-write`.
- Reviewer and Executive packets use `read-only`.

Override cautiously:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter codex-cli \
  --role reviewer \
  --baton B-001 \
  --codex-sandbox read-only \
  --codex-model gpt-5 \
  --experimental
```

## Lock Guard

Write-capable packets require a held lock for the baton. This protects shared
worktrees from accidental concurrent writers.

If you intentionally manage isolation outside the DB, such as with a separate
worktree, pass:

```bash
--allow-unlocked
```

Only use this when the merge and reconciliation plan is clear.

## Timeouts And Output

Defaults:

- timeout: 1800 seconds;
- output capture: 20000 characters per stream.

Adjust with:

```bash
--timeout-seconds 3600
--output-limit 50000
```

Timeouts return status `timed_out` and exit code `124`. Missing executables
return exit code `127`.

## Event Records

Real executions record:

- `agent.spawn.started`
- `agent.spawn.completed`

The event payload includes session id, adapter, role, baton id, packet path,
timeout, command preview, status, return code, and duration.

Real executions also create or update an `agent_sessions` row. The session row
stores bounded stdout/stderr in `metadata_json` so the dashboard can show
completed process output. Event payloads keep only compact audit metadata.

Use `--no-event` only for experiments where durable audit records are not
appropriate.

## Dashboard Visibility

The optional dashboard reads `agent_sessions` to show adapter-spawned workers:

```bash
python3 /path/to/agentic-factory/scripts/factory.py dashboard serve --open
```

Process adapters are visible but not live-steerable. Dashboard message controls
are enabled by default and record `agent.message.requested` events unless a
future session-backed adapter provides live delivery. Start the dashboard with
`--read-only` when those control records should be disabled.

## When Not To Use Adapters

Do not use adapters when:

- Codex-native orchestration is available and sufficient;
- the command may prompt interactively;
- credentials or secrets may leak through command arguments;
- workspace ownership is unclear;
- a write-capable worker would share a worktree without a held lock;
- cancellation or recovery behavior is unknown;
- the adapter would need production access or irreversible external effects.
