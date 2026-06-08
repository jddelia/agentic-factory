# Agent Adapters

Agent adapters bridge Agentic Factory packets to external agent CLI sessions or
processes. They are useful when a runtime does not provide Codex-native visible
threads but can run a separate local agent session from the shell.

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
- enforces bounded launch or process timeouts;
- captures bounded launch/process stdout and stderr;
- creates an `agent_sessions` row for real executions;
- records `agent.spawn.started` and `agent.spawn.completed` events for real
  executions unless `--no-event` is supplied.

Session-backed adapters may return immediately with a live external session
reference. Process adapters block until the child exits. The command does not
create a native Codex app thread.

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

## Claude Code Background-Session Adapter

Use `claude-code` when the local Claude Code CLI is installed, authenticated,
and supports background sessions:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent spawn \
  --adapter claude-code \
  --role builder \
  --baton B-001 \
  --permission-profile node-builder \
  --experimental
```

The adapter launches `claude --bg`, loads this plugin with `--plugin-dir` by
default, writes a packet file, and asks the new background session to read that
packet. On success it returns quickly with:

- the Agentic Factory session id;
- the Claude Code background session id in `control_ref`;
- `claude attach <id>`, `claude logs <id>`, and `claude stop <id>` commands in
  session metadata;
- an `agent_sessions` row with `control_mode: claude_bg`.

Useful options:

```bash
--claude-bin claude
--claude-model sonnet
--claude-agent builder
--claude-permission-mode plan
--permission-profile node-builder
--claude-worktree
--claude-worktree feature-baton-001
--claude-plugin-dir /path/to/another-plugin
--claude-no-plugin-dir
--claude-add-dir /path/to/shared-context
```

Use `--claude-worktree` for isolated write-capable work when the merge plan is
clear. Without it, the factory lock still enforces the one-writer rule for the
shared worktree.

The adapter follows the current Claude Code CLI background-session contract:
`claude --bg` starts a visible background session, `claude agents --json`
reports session state, and `claude attach`, `claude logs`, and `claude stop`
control that session.

## Adapter Capabilities And Permissions

Inspect adapter capabilities:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent adapter list --json
python3 /path/to/agentic-factory/scripts/factory.py agent adapter doctor --adapter claude-code
```

Permission profiles are adapter-neutral:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent permissions list --json
python3 /path/to/agentic-factory/scripts/factory.py agent permissions plan \
  --adapter claude-code \
  --profile node-builder
```

Current built-in profiles include:

- `read-only`
- `node-builder`
- `node-reviewer`
- `workspace-builder`

Each adapter returns a translation report with `enforced`, `advisory`, and
`unsupported` fields. Claude Code profiles translate to native permission
flags such as permission mode, allowed tools, and disallowed tools. Codex CLI
profiles translate to sandbox/approval choices where possible. Custom adapters
receive the profile inside the packet, but most fields are advisory unless the
custom runner enforces them.

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
- `agent.spawn.completed` for process adapters and failed session launches
- `agent.session.synced` when live adapter state is refreshed
- `agent.session.stopped` when a live session is stopped through the CLI

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
future transport provides live delivery. Claude Code background sessions are
attachable: the dashboard shows attach/log/stop commands, and snapshots refresh
active Claude Code session state through bounded `claude agents --json` sync.
Start the dashboard with `--read-only` when control records should be disabled.

## Session Inspection

List sessions:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent session list --sync
```

Show one session:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent session show claude-7c5dcf5d --json
```

Refresh live adapter state:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent session sync --adapter claude-code
```

Read logs or stop a live Claude Code session:

```bash
python3 /path/to/agentic-factory/scripts/factory.py agent session logs claude-7c5dcf5d
python3 /path/to/agentic-factory/scripts/factory.py agent session stop claude-7c5dcf5d
```

## When Not To Use Adapters

Do not use adapters when:

- Codex-native orchestration is available and sufficient;
- the command may prompt interactively;
- credentials or secrets may leak through command arguments;
- workspace ownership is unclear;
- a write-capable worker would share a worktree without a held lock;
- cancellation or recovery behavior is unknown;
- the adapter would need production access or irreversible external effects.
