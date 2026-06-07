# CLI Reference

This file is generated from `scripts/factory.py --help` output.
Update it with:

```bash
python3 scripts/generate_cli_docs.py --write
```

Global options apply before the command name:

- `--root <path>`: target project root; defaults to the current working directory.
- `--db <path>`: SQLite DB path; relative paths resolve under `--root`.
- `--config <path>`: project config path; relative paths resolve under `--root`.

The CLI is local-first and stdlib-only. It does not execute shell input from command arguments. Process spawning is limited to explicit experimental `agent spawn` adapters.

## `factory.py`

```text
usage: factory.py [-h] [--root ROOT] [--db DB] [--config CONFIG]
                  {config,init,up,status,dashboard,agent,event,baton,verify,review,pause,resume,lock,events,verification,render-ledger,doctor} ...

SQLite-backed software factory CLI.

positional arguments:
  {config,init,up,status,dashboard,agent,event,baton,verify,review,pause,resume,lock,events,verification,render-ledger,doctor}
    config              Create or show project config.
    init                Initialize a factory DB.
    up                  Initialize the factory floor and serve the local dashboard.
    status              Show current factory state.
    dashboard           Inspect or serve the local factory dashboard.
    agent               Generate portable agent packets.
    event               Record a raw event.
    baton               Create, hand off, or accept batons.
    verify              Record verification commands.
    review              Record review packets.
    pause               Pause the factory.
    resume              Resume the factory.
    lock                Manage explicit locks.
    events              Inspect recorded events.
    verification        Inspect verification records.
    render-ledger       Render markdown ledger from DB.
    doctor              Run factory health checks.

options:
  -h, --help            show this help message and exit
  --root ROOT           Project root; defaults to current directory.
  --db DB               Factory DB path; defaults to .agentic-factory/factory.db.
  --config CONFIG       Project config path; defaults to .agentic-factory/config.json.
```

Use global options before the command name.

Example:

```bash
python3 scripts/factory.py --root /path/to/project --db state/factory.sqlite status --json
```

Common failures:

- No command: argparse prints usage and exits non-zero.
- Relative `--db`: resolved under `--root`, not the shell's original directory.

## `factory.py config`

```text
usage: factory.py config [-h] {init,show} ...

positional arguments:
  {init,show}
    init       Create .agentic-factory/config.json.
    show       Show effective project config.

options:
  -h, --help   show this help message and exit
```

## `factory.py config init`

```text
usage: factory.py config init [-h] [--force]

options:
  -h, --help  show this help message and exit
  --force
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py config init
```

Example output shape:

```json
{"status": "created", "path": ".../.agentic-factory/config.json", "config": {...}}
```

Common failures:

- Config already exists and `--force` was not supplied.
- The target config path cannot be written.

## `factory.py config show`

```text
usage: factory.py config show [-h]

options:
  -h, --help  show this help message and exit
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py config show
```

Example output shape:

```json
{"path": ".../.agentic-factory/config.json", "exists": true, "config": {...}}
```

Common failures:

- Config JSON is invalid.
- Config contains unknown fields or unsafe relative paths.

## `factory.py init`

```text
usage: factory.py init [-h] [--mode MODE] [--objective OBJECTIVE] [--topology TOPOLOGY]
                       [--actor ACTOR] [--run-id RUN_ID] [--force]

options:
  -h, --help            show this help message and exit
  --mode MODE
  --objective OBJECTIVE
  --topology TOPOLOGY
  --actor ACTOR
  --run-id RUN_ID
  --force
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py init --mode balanced --objective "Ship the requested outcome"
```

Example output shape:

```json
{"status": "initialized", "db": ".../.agentic-factory/factory.db", "run_id": "..."}
```

Common failures:

- Existing run without `--force`: returns `status: exists` without creating a new run.
- Invalid migration filename: exits with a `factory: error:` message.

## `factory.py up`

```text
usage: factory.py up [-h] [--mode MODE] [--objective OBJECTIVE] [--topology TOPOLOGY]
                     [--runtime-mode {adapter_spawn,agent_cli_subagents,codex_native,manual_protocol,serial_single_agent}]
                     [--actor ACTOR] [--run-id RUN_ID] [--force] [--host HOST] [--port PORT]
                     [--recent RECENT] [--token TOKEN] [--read-only] [--allow-remote] [--open]
                     [--no-open] [--background] [--no-serve]

options:
  -h, --help            show this help message and exit
  --mode MODE
  --objective OBJECTIVE
  --topology TOPOLOGY
  --runtime-mode {adapter_spawn,agent_cli_subagents,codex_native,manual_protocol,serial_single_agent}
                        Resolved runtime mode from the orchestration skill.
  --actor ACTOR
  --run-id RUN_ID
  --force               Create a new run even if one already exists.
  --host HOST
  --port PORT           Dashboard port; defaults to first free port from 8765.
  --recent RECENT
  --token TOKEN         Access token; generated by default.
  --read-only           Disable dashboard control endpoints.
  --allow-remote        Allow binding to a non-loopback host.
  --open                Open the dashboard URL in the default browser. This is the default.
  --no-open             Do not open the dashboard URL.
  --background          Start the dashboard server in the background and print JSON.
  --no-serve            Test-only bootstrap without starting the dashboard server.
```

Required arguments: none, but orchestration agents should pass a resolved
objective, mode, topology, and runtime mode after using
`agentic-factory-orchestration`.

`up` is the low-friction agent-facing bootstrap. It initializes the DB
if needed, ensures operator records, starts the local dashboard with
controls enabled by default, records readiness events, and prints the
URL. If the default port is occupied, it picks the next free port. It
does not assign the first baton.

For real agent CLI invocations, use `--background` so the dashboard
server keeps running while the agent receives JSON and can pause for
user readiness.

Example:

```bash
python3 scripts/factory.py up --objective "Build the todo app" --topology executive_as_ledger --background
```

Test-only setup without a running dashboard:

```bash
python3 scripts/factory.py up --objective "Build the todo app" --no-serve --no-open
```

Example output shape with `--background`:

```json
{"status": "ready_for_user", "dashboard_url": "http://127.0.0.1:8765/?token=...", "server_running": true, "dashboard_pid": 12345}
```

Common failures:

- Dashboard assets are missing: run `cd dashboard && npm install && npm run build`.
- Non-loopback host without `--allow-remote`.
- `--port` is outside the allowed range.
- Explicit `--port` is already in use.
- `--background` and `--no-serve` are used together.
- Existing run plus `--force` with a duplicate `--run-id`.

## `factory.py status`

```text
usage: factory.py status [-h] [--json] [--compact]

options:
  -h, --help  show this help message and exit
  --json
  --compact
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py status --compact
```

Example output shape:

```text
factory=<id> status=active mode=balanced
active_batons=0 held_locks=0
latest_baton=none status=none
git=<head or unavailable>
```

Common failures:

- No run exists: initialize first with `factory.py init`.

## `factory.py dashboard`

```text
usage: factory.py dashboard [-h] {snapshot,serve} ...

positional arguments:
  {snapshot,serve}
    snapshot        Print the dashboard read model as JSON.
    serve           Serve the local dashboard UI.

options:
  -h, --help        show this help message and exit
```

## `factory.py dashboard snapshot`

```text
usage: factory.py dashboard snapshot [-h] [--recent RECENT]

options:
  -h, --help       show this help message and exit
  --recent RECENT
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py dashboard snapshot --recent 50
```

Example output shape:

```json
{"initialized": true, "metrics": {"active_batons": 1}, "sessions": []}
```

Common failures:

- `--recent` is outside the allowed range.

## `factory.py dashboard serve`

```text
usage: factory.py dashboard serve [-h] [--host HOST] [--port PORT] [--recent RECENT]
                                  [--token TOKEN] [--open] [--enable-control] [--read-only]
                                  [--actor ACTOR] [--allow-remote]

options:
  -h, --help        show this help message and exit
  --host HOST
  --port PORT       Dashboard port; defaults to first free port from 8765.
  --recent RECENT
  --token TOKEN     Access token; generated by default.
  --open            Open the dashboard URL in the default browser.
  --enable-control  Deprecated compatibility flag; controls are enabled by default.
  --read-only       Disable dashboard control endpoints.
  --actor ACTOR
  --allow-remote    Allow binding to a non-loopback host. A token is still required.
```

Required arguments: none.

The default dashboard server is dependency-free and uses the Python
standard library. It requires prebuilt frontend assets under
`dashboard/dist`. If the default port is occupied, it picks the next
free port unless `--port` is supplied explicitly.

Example:

```bash
python3 scripts/factory.py dashboard serve --open
```

Control endpoints are enabled by default. Use read-only mode when
observation is desired without dashboard message controls:

```bash
python3 scripts/factory.py dashboard serve --read-only
```

Common failures:

- Dashboard assets are missing: run `cd dashboard && npm install && npm run build`.
- Non-loopback host without `--allow-remote`.
- `--port` is outside the allowed range.
- Explicit `--port` is already in use.

## `factory.py agent`

```text
usage: factory.py agent [-h] {packet,spawn} ...

positional arguments:
  {packet,spawn}
    packet        Generate a role packet for delegation.
    spawn         Experimentally spawn a packet through an adapter.

options:
  -h, --help      show this help message and exit
```

## `factory.py agent packet`

```text
usage: factory.py agent packet [-h] --role {builder,executive,reviewer} [--baton BATON]
                               [--recent RECENT] [--format {json,markdown}]
                               [--runtime-mode {adapter_spawn,agent_cli_subagents,codex_native,manual_protocol,serial_single_agent}]
                               [--write-policy {auto,read-only,write}] [--allowed ALLOWED]
                               [--restricted RESTRICTED] [--invariant INVARIANT]
                               [--required-check REQUIRED_CHECK] [--non-goal NON_GOAL]

options:
  -h, --help            show this help message and exit
  --role {builder,executive,reviewer}
  --baton BATON
  --recent RECENT
  --format {json,markdown}
  --runtime-mode {adapter_spawn,agent_cli_subagents,codex_native,manual_protocol,serial_single_agent}
  --write-policy {auto,read-only,write}
  --allowed ALLOWED     Allowed file or area; repeat or comma-separate.
  --restricted RESTRICTED
                        Restricted file or area; repeat or comma-separate.
  --invariant INVARIANT
                        Hard invariant to include.
  --required-check REQUIRED_CHECK
                        Required check to include.
  --non-goal NON_GOAL   Non-goal to include.
```

Required arguments: `--role`.

Builder and Reviewer packets also require `--baton`.

Example:

```bash
python3 scripts/factory.py agent packet --role builder --baton B-001
```

Structured output:

```bash
python3 scripts/factory.py agent packet --role reviewer --baton B-001 --format json
```

Example output shape:

```json
{"packet_version": 1, "role": "builder", "baton": {"id": "B-001"}, "recording_commands": []}
```

Common failures:

- No run exists.
- Unknown baton when `--baton` is supplied.
- `--baton` is missing for Builder or Reviewer packets.
- `--recent` is outside the allowed range.

## `factory.py agent spawn`

```text
usage: factory.py agent spawn [-h] --adapter {codex-cli,custom} [--experimental] [--dry-run]
                              --role {builder,executive,reviewer} [--baton BATON]
                              [--recent RECENT] [--packet-format {json,markdown}]
                              [--packet-dir PACKET_DIR] [--write-policy {auto,read-only,write}]
                              [--allowed ALLOWED] [--restricted RESTRICTED]
                              [--invariant INVARIANT] [--required-check REQUIRED_CHECK]
                              [--non-goal NON_GOAL] [--command COMMAND]
                              [--timeout-seconds TIMEOUT_SECONDS] [--output-limit OUTPUT_LIMIT]
                              [--allow-unlocked] [--no-event] [--actor ACTOR]
                              [--codex-bin CODEX_BIN] [--codex-model CODEX_MODEL]
                              [--codex-profile CODEX_PROFILE]
                              [--codex-sandbox {auto,read-only,workspace-write}]
                              [--codex-approval {never,on-failure,on-request,untrusted}]
                              [--codex-skip-git-repo-check]

options:
  -h, --help            show this help message and exit
  --adapter {codex-cli,custom}
  --experimental        Required to execute the adapter.
  --dry-run             Write packet and print argv without execution.
  --role {builder,executive,reviewer}
  --baton BATON
  --recent RECENT
  --packet-format {json,markdown}
  --packet-dir PACKET_DIR
  --write-policy {auto,read-only,write}
  --allowed ALLOWED     Allowed file or area; repeat or comma-separate.
  --restricted RESTRICTED
                        Restricted file or area; repeat or comma-separate.
  --invariant INVARIANT
                        Hard invariant to include.
  --required-check REQUIRED_CHECK
                        Required check to include.
  --non-goal NON_GOAL   Non-goal to include.
  --command COMMAND     Custom adapter command template; must include {packet}.
  --timeout-seconds TIMEOUT_SECONDS
  --output-limit OUTPUT_LIMIT
  --allow-unlocked      Allow write-capable spawn without a held baton lock.
  --no-event            Do not record agent.spawn events.
  --actor ACTOR
  --codex-bin CODEX_BIN
  --codex-model CODEX_MODEL
  --codex-profile CODEX_PROFILE
  --codex-sandbox {auto,read-only,workspace-write}
  --codex-approval {never,on-failure,on-request,untrusted}
  --codex-skip-git-repo-check
```

Required arguments: `--adapter`, `--role`.

Builder and Reviewer spawns also require `--baton`. Custom spawns require
`--command` with a `{packet}` placeholder. Real execution requires
`--experimental`; use `--dry-run` to preview without execution.

Example dry run:

```bash
python3 scripts/factory.py agent spawn --adapter custom --role builder --baton B-001 --command "my-agent run --prompt-file {packet}" --dry-run
```

Example Codex CLI execution:

```bash
python3 scripts/factory.py agent spawn --adapter codex-cli --role builder --baton B-001 --experimental
```

Example output shape:

```json
{"status": "completed", "adapter": "custom", "packet_path": "...", "returncode": 0}
```

Common failures:

- Missing `--experimental` for real execution.
- Missing `{packet}` in a custom command.
- Unknown baton or missing baton for Builder/Reviewer.
- Write-capable spawn has no held baton lock and `--allow-unlocked` was not supplied.
- Timeout returns status `timed_out` and exit code `124`.
- Missing executable returns exit code `127`.

## `factory.py event`

```text
usage: factory.py event [-h] {append} ...

positional arguments:
  {append}
    append    Append a structured event.

options:
  -h, --help  show this help message and exit
```

## `factory.py event append`

```text
usage: factory.py event append [-h] --type TYPE [--actor ACTOR] [--baton BATON]
                               [--summary SUMMARY] [--payload PAYLOAD]
                               [--payload-file PAYLOAD_FILE]

options:
  -h, --help            show this help message and exit
  --type TYPE
  --actor ACTOR
  --baton BATON
  --summary SUMMARY
  --payload PAYLOAD
  --payload-file PAYLOAD_FILE
```

Required arguments: `--type`.

Example:

```bash
python3 scripts/factory.py event append --type factory.note --summary "Checkpoint reached"
```

Example output shape:

```json
{"status": "recorded", "event_type": "factory.note", "baton": null}
```

Common failures:

- No run exists.
- `--payload` and `--payload-file` used together.
- Payload is not a JSON object.

## `factory.py baton`

```text
usage: factory.py baton [-h] {list,show,create,handoff,accept} ...

positional arguments:
  {list,show,create,handoff,accept}
    list                List batons for the current run.
    show                Show detailed baton evidence.
    create              Assign a baton and acquire the writer lock.
    handoff             Record a baton handoff.
    accept              Accept a baton.

options:
  -h, --help            show this help message and exit
```

## `factory.py baton list`

```text
usage: factory.py baton list [-h] [--all] [--status STATUS] [--limit LIMIT] [--json]

options:
  -h, --help       show this help message and exit
  --all            Include non-active batons.
  --status STATUS  Filter by status; repeat or comma-separate.
  --limit LIMIT
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py baton list --all --json
```

Example output shape:

```json
{"count": 1, "batons": [{"id": "B-001", "status": "accepted"}]}
```

Common failures:

- No run exists.
- `--limit` is less than 1 or greater than the maximum list limit.

## `factory.py baton show`

```text
usage: factory.py baton show [-h] [--recent-events RECENT_EVENTS] [--json] baton_id

positional arguments:
  baton_id

options:
  -h, --help            show this help message and exit
  --recent-events RECENT_EVENTS
  --json
```

Required arguments: `baton_id`.

Example:

```bash
python3 scripts/factory.py baton show B-001 --json
```

Example output shape:

```json
{"baton": {...}, "handoffs": [], "verification": [], "reviews": [], "commits": [], "events": []}
```

Common failures:

- Unknown baton.
- Baton does not belong to the current run.
- `--recent-events` is outside the allowed range.

## `factory.py baton create`

```text
usage: factory.py baton create [-h] --title TITLE [--owner OWNER] [--owner-thread OWNER_THREAD]
                               [--scope SCOPE] [--summary SUMMARY]
                               [--acceptance-tier ACCEPTANCE_TIER]
                               [--verification-level VERIFICATION_LEVEL] [--model MODEL]
                               [--reasoning REASONING] [--actor ACTOR] [--allow-active]
                               [--no-lock] [--lock-name LOCK_NAME] [--force-lock]
                               baton_id

positional arguments:
  baton_id

options:
  -h, --help            show this help message and exit
  --title TITLE
  --owner OWNER
  --owner-thread OWNER_THREAD
  --scope SCOPE
  --summary SUMMARY
  --acceptance-tier ACCEPTANCE_TIER
  --verification-level VERIFICATION_LEVEL
  --model MODEL
  --reasoning REASONING
  --actor ACTOR
  --allow-active
  --no-lock
  --lock-name LOCK_NAME
  --force-lock
```

Required arguments: `baton_id`, `--title`.

Example:

```bash
python3 scripts/factory.py baton create B-001 --title "First slice" --owner Builder
```

Example output shape:

```json
{"status": "assigned", "baton": "B-001", "lock": "main-worktree"}
```

Common failures:

- No run exists.
- Another active baton exists and `--allow-active` was not supplied.
- Writer lock is already held and `--force-lock` was not supplied.
- Project config is invalid.

## `factory.py baton handoff`

```text
usage: factory.py baton handoff [-h] [--owner OWNER] --summary SUMMARY [--behavior BEHAVIOR]
                                [--files FILES] [--commands COMMANDS]
                                [--verification VERIFICATION] [--risks RISKS] [--next NEXT]
                                [--actor ACTOR] [--release-lock] [--keep-lock]
                                [--lock-name LOCK_NAME]
                                baton_id

positional arguments:
  baton_id

options:
  -h, --help            show this help message and exit
  --owner OWNER
  --summary SUMMARY
  --behavior BEHAVIOR
  --files FILES
  --commands COMMANDS
  --verification VERIFICATION
  --risks RISKS
  --next NEXT
  --actor ACTOR
  --release-lock
  --keep-lock
  --lock-name LOCK_NAME
```

Required arguments: `baton_id`, `--summary`.

Example:

```bash
python3 scripts/factory.py baton handoff B-001 --summary "Implemented" --commands "python3 -m unittest"
```

Example output shape:

```json
{"status": "handed_off", "baton": "B-001", "lock_released": true}
```

Common failures:

- Unknown baton.
- No run exists.
- Project config is invalid.

## `factory.py baton accept`

```text
usage: factory.py baton accept [-h] [--commit COMMIT] [--message MESSAGE]
                               [--pushed-status PUSHED_STATUS] [--summary SUMMARY] [--actor ACTOR]
                               [--release-lock] [--keep-lock] [--lock-name LOCK_NAME]
                               baton_id

positional arguments:
  baton_id

options:
  -h, --help            show this help message and exit
  --commit COMMIT
  --message MESSAGE
  --pushed-status PUSHED_STATUS
  --summary SUMMARY
  --actor ACTOR
  --release-lock
  --keep-lock
  --lock-name LOCK_NAME
```

Required arguments: `baton_id`.

Example:

```bash
python3 scripts/factory.py baton accept B-001 --commit abc1234 --summary "Accepted"
```

Example output shape:

```json
{"status": "accepted", "baton": "B-001", "commit": "abc1234"}
```

Common failures:

- Unknown baton.
- Accepting before the configured tier is satisfied is an orchestration error; the CLI records the decision you give it.
- Project config is invalid.

## `factory.py verify`

```text
usage: factory.py verify [-h] {list,record} ...

positional arguments:
  {list,record}
    list         List verification records.

options:
  -h, --help     show this help message and exit
```

## `factory.py verify list`

```text
usage: factory.py verify list [-h] [--baton BATON] [--recent RECENT] [--json]

options:
  -h, --help       show this help message and exit
  --baton BATON
  --recent RECENT
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py verify list --baton B-001 --json
```

Example output shape:

```json
{"count": 1, "verification": [{"result": "pass", "command": "pytest"}]}
```

Common failures:

- No run exists.
- Unknown baton when `--baton` is supplied.
- `--recent` is outside the allowed range.

## `factory.py verify record`

```text
usage: factory.py verify record [-h] [--baton BATON] --command COMMAND --result RESULT
                                [--package PACKAGE] [--duration-ms DURATION_MS]
                                [--summary SUMMARY] [--actor ACTOR] [--payload PAYLOAD]
                                [--payload-file PAYLOAD_FILE]

options:
  -h, --help            show this help message and exit
  --baton BATON
  --command COMMAND
  --result RESULT
  --package PACKAGE
  --duration-ms DURATION_MS
  --summary SUMMARY
  --actor ACTOR
  --payload PAYLOAD
  --payload-file PAYLOAD_FILE
```

Required arguments: `--command`, `--result`.

Example:

```bash
python3 scripts/factory.py verify record --baton B-001 --command "python3 -m unittest" --result pass
```

Example output shape:

```json
{"status": "recorded", "result": "pass", "command": "python3 -m unittest"}
```

Common failures:

- `--result` is not one of `pass`, `fail`, `not_run`, or `blocked`.
- `--duration-ms` is negative.
- Unknown baton when `--baton` is supplied.
- Project config requires `--baton`.
- Project config requires `--summary` for `not_run`.

## `factory.py review`

```text
usage: factory.py review [-h] {list,record} ...

positional arguments:
  {list,record}
    list         List review records.

options:
  -h, --help     show this help message and exit
```

## `factory.py review list`

```text
usage: factory.py review list [-h] [--baton BATON] [--recent RECENT] [--json]

options:
  -h, --help       show this help message and exit
  --baton BATON
  --recent RECENT
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py review list --baton B-001 --json
```

Example output shape:

```json
{"count": 1, "reviews": [{"status": "accepted", "findings": []}]}
```

Common failures:

- No run exists.
- Unknown baton when `--baton` is supplied.
- `--recent` is outside the allowed range.

## `factory.py review record`

```text
usage: factory.py review record [-h] --baton BATON [--reviewer REVIEWER]
                                [--reviewer-thread REVIEWER_THREAD] [--status STATUS]
                                [--summary SUMMARY] [--finding FINDING] [--actor ACTOR]
                                [--payload PAYLOAD] [--payload-file PAYLOAD_FILE]

options:
  -h, --help            show this help message and exit
  --baton BATON
  --reviewer REVIEWER
  --reviewer-thread REVIEWER_THREAD
  --status STATUS
  --summary SUMMARY
  --finding FINDING
  --actor ACTOR
  --payload PAYLOAD
  --payload-file PAYLOAD_FILE
```

Required arguments: `--baton`.

Example:

```bash
python3 scripts/factory.py review record --baton B-001 --status accepted --summary "No blockers"
```

Example output shape:

```json
{"status": "recorded", "review_id": 1, "findings": 0}
```

Common failures:

- Unknown baton.
- Finding does not use `severity|file|line|status|summary`.
- Finding line is not blank, `0`, or an integer.

## `factory.py pause`

```text
usage: factory.py pause [-h] [--mode MODE] [--reason REASON] [--actor ACTOR]

options:
  -h, --help       show this help message and exit
  --mode MODE
  --reason REASON
  --actor ACTOR
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py pause --mode drain_to_checkpoint --reason "User review"
```

Example output shape:

```json
{"status": "paused", "mode": "drain_to_checkpoint", "reason": "User review"}
```

Common failures:

- No run exists.

## `factory.py resume`

```text
usage: factory.py resume [-h] [--reason REASON] [--actor ACTOR]

options:
  -h, --help       show this help message and exit
  --reason REASON
  --actor ACTOR
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py resume --reason "User approved next baton"
```

Example output shape:

```json
{"status": "active", "reason": "User approved next baton"}
```

Common failures:

- No run exists.
- Resuming unclear ownership should be handled by orchestration recovery before new baton assignment.

## `factory.py lock`

```text
usage: factory.py lock [-h] {acquire,release} ...

positional arguments:
  {acquire,release}

options:
  -h, --help         show this help message and exit
```

## `factory.py lock acquire`

```text
usage: factory.py lock acquire [-h] [--name NAME] --holder HOLDER [--baton BATON] [--force]

options:
  -h, --help       show this help message and exit
  --name NAME
  --holder HOLDER
  --baton BATON
  --force
```

Required arguments: `--holder`.

Example:

```bash
python3 scripts/factory.py lock acquire --holder Builder --baton B-001
```

Example output shape:

```json
{"status": "held", "lock": "main-worktree", "holder": "Builder"}
```

Common failures:

- Lock already held and `--force` was not supplied.
- No run exists.

## `factory.py lock release`

```text
usage: factory.py lock release [-h] [--name NAME] [--actor ACTOR]

options:
  -h, --help     show this help message and exit
  --name NAME
  --actor ACTOR
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py lock release --name main-worktree
```

Example output shape:

```json
{"status": "released", "lock": "main-worktree"}
```

Common failures:

- No run exists.
- Releasing a missing lock is idempotent at the table-update level.
- Project config is invalid.

## `factory.py events`

```text
usage: factory.py events [-h] {list} ...

positional arguments:
  {list}
    list      List recent events.

options:
  -h, --help  show this help message and exit
```

## `factory.py events list`

```text
usage: factory.py events list [-h] [--recent RECENT] [--baton BATON] [--type TYPE] [--json]

options:
  -h, --help       show this help message and exit
  --recent RECENT
  --baton BATON
  --type TYPE
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py events list --recent 20 --json
```

Example output shape:

```json
{"count": 1, "events": [{"event_type": "factory.started"}]}
```

Common failures:

- No run exists.
- Unknown baton when `--baton` is supplied.
- `--recent` is outside the allowed range.

## `factory.py verification`

```text
usage: factory.py verification [-h] {list} ...

positional arguments:
  {list}
    list      List verification records.

options:
  -h, --help  show this help message and exit
```

## `factory.py verification list`

```text
usage: factory.py verification list [-h] [--baton BATON] [--recent RECENT] [--json]

options:
  -h, --help       show this help message and exit
  --baton BATON
  --recent RECENT
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py verification list --baton B-001 --json
```

Example output shape:

```json
{"count": 1, "verification": [{"result": "pass", "command": "pytest"}]}
```

Common failures:

- No run exists.
- Unknown baton when `--baton` is supplied.
- `--recent` is outside the allowed range.

## `factory.py render-ledger`

```text
usage: factory.py render-ledger [-h] [--out OUT] [--recent RECENT]

options:
  -h, --help       show this help message and exit
  --out OUT
  --recent RECENT
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py render-ledger --out docs/build_ledger.md --recent 20
```

Example output shape:

```json
{"status": "rendered", "out": ".../docs/build_ledger.md", "recent": 20}
```

Common failures:

- No run exists.
- `--recent` is less than 1.
- Project config has an unsafe `ledger_output_path`.

## `factory.py doctor`

```text
usage: factory.py doctor [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json
```

Required arguments: none.

Example:

```bash
python3 scripts/factory.py doctor --json
```

Example output shape:

```json
{"status": "ok", "findings": [{"level": "ok", "check": "schema", "message": "..."}]}
```

Common failures:

- No run exists.
- Failing health checks return a non-zero exit code.
