---
name: agentic-factory-orchestration
description: Use when instantiating or running a full agentic software factory with work modes, roles, topology, batons, review policy, verification cadence, stop/resume controls, recovery, release gates, user feedback routing, and optional DB-backed state through the agentic-factory CLI skill.
---

# Agentic Factory Orchestration

Use this skill when the user wants Codex to run a complete software factory,
not merely record a factory event. It defines the public operating model for
agentic project execution.

When durable state is useful or already initialized, use the `agentic-factory`
skill as the CLI/state layer for `init`, `status`, `doctor`, baton records,
verification records, review records, pause/resume checkpoints, and rendered
ledgers.

The primary runtime is the Codex app. Prefer Codex-native thread or sub-agent
capabilities when they are available and safe for the selected work. Other
agent CLIs may approximate the same factory model through their own delegation
features, generated agent packets, visible background sessions, or serial role
simulation. The `factory.py` CLI records state, renders packets, can expose an
optional dashboard, and can run explicitly authorized session/process adapter
spawns.

## Required Sequence

This sequence is a contract, not a recommendation. Violating it is incorrect
behavior regardless of task size, project clarity, or implementation urgency.

For generic agent CLI runtimes, or whenever Codex-native visible worker threads
are not available, follow these hard stops in order:

1. Inspect only enough project and factory state to identify the repository,
   existing `.agentic-factory` state, dirty worktree, obvious stack, likely
   checks, and available runtime/delegation capabilities.
2. Resolve the startup configuration: objective, hard constraints, work mode,
   topology, runtime mode, verification policy, dashboard policy, and session
   strategy. Inferring safe defaults is allowed; skipping presentation of those
   defaults is not.
3. Present the resolved startup brief to the user and ask for confirmation or
   missing information in normal chat. Ask at most three questions. Do not use
   a special user-input tool unless the runtime explicitly provides one.
4. After confirmation, run `factory.py up --background` from the target
   project root. In agent-CLI dashboard workflows, `up` is the first mutating
   factory command, and `--background` is the non-blocking mode that still
   starts the dashboard server.
5. PAUSE. Present the dashboard URL, run ID, project root, topology, runtime
   mode, control state, and top-level operator. Wait for the user to say that
   factory operations may begin.
6. Only after the user confirms readiness, run `status --compact`, `doctor`,
   create the first baton, generate packets, spawn workers, or edit project
   files.

Before step 5 is complete, do not run `baton create`, `agent packet`,
`agent spawn`, implementation commands, file edits, or acceptance commands.

For Codex-native runtimes with visible native worker threads, use native
thread orchestration as the primary UI. Durable state is still required, but
`init` may replace `up` only when the Codex app already provides the visible
factory floor and the user does not need the local dashboard.

## Outcome

Create a factory that matches the project's risk, maturity, and delivery target:

- explicit work mode and target outcome;
- one Executive with final product and quality authority;
- optional Principal Partner for long-running user-facing oversight;
- Executive-as-ledger by default, with separate ledger only when scale justifies
  it;
- one active writer per worktree by default;
- optional read-only Reviewers and feedback Manager/User Liaison;
- explicit baton lifecycle, handoff evidence, review policy, and acceptance tier;
- explicit stop/resume controls with recoverable state;
- explicit runtime mode and delegation capability preflight;
- optional local dashboard visibility for agent-CLI factory floors;
- explicit permission, model, approval, destructive-action, credential, and
  external-effect policy;
- commits only for accepted work unless the user explicitly delegates otherwise.

Do not hard-code project-specific rules. Infer invariants from the repository,
user request, project docs, tests, risk surface, and local tool constraints.

## First Move

1. Inspect before assigning work: stack, scripts, docs, dirty git state, branch,
   remote, generated-file hazards, test commands, env/secrets expectations,
   permission constraints, browser/tool availability, active factory state, and
   runtime delegation capabilities.
2. Choose the runtime mode:
   - `codex_native`: preferred when Codex-native worker delegation is available.
   - `agent_cli_subagents`: use another CLI's sub-agent mechanism after
     capability preflight.
   - `adapter_spawn`: use a first-class session adapter when the host CLI's
     best delegation path is a visible background session, especially
     `claude-code`.
   - `serial_single_agent`: use only when delegation is unavailable, ambiguous,
     or unsafe.
   - `manual_protocol`: use for tests, demos, and human debugging.
3. Choose or confirm a compact configuration:
   - `work_mode`: default `balanced` unless the request clearly implies another
     mode.
   - `factory_topology`: default `executive_as_ledger`.
   - `role_topology`: default `reviewed` for substantial work, `lean_solo` for
     small tasks.
   - `acceptance_tier`: default `integration`; use `release` only for ship
     readiness.
   - `verification_level`: default `focused_plus_build` for normal feature work.
   - `concurrency_policy`: default `single_writer`.
4. For agent-CLI dashboard workflows, call `agentic-factory` `up` after this
   preflight, present the dashboard URL/run/topology/runtime/operator values,
   and pause until the user confirms factory operations can begin.
5. For Codex-native or state-only DB-backed factories, initialize or inspect
   state with `agentic-factory`: `init`, `status --compact`, then `doctor`.
6. Define the next baton with objective, scope, non-goals, risk, acceptance tier,
   verification level, escalation triggers, owner, and handoff requirements.
7. Assign only the roles needed for the chosen topology and runtime mode.

Ask at most three short questions when required. If the user's request gives
enough signal, infer defaults, present them for confirmation, then proceed only
after the required startup sequence allows it.

## Runtime Modes

- `codex_native`: primary and preferred. Use Codex-native threads or sub-agents
  to delegate Builder, Reviewer, Manager/User Liaison, Watcher, or Ledger work
  when the host exposes those tools. Record baton state before delegation.
- `agent_cli_subagents`: use when another agent CLI has a clear, safe
  sub-agent or background-session mechanism. Let that CLI own native spawning
  when possible; pass scoped baton or review packets from `factory.py agent
  packet` and record returned evidence through `agentic-factory`.
- `adapter_spawn`: explicit adapters that launch external agent CLI sessions or
  processes from generated packets. Prefer the `claude-code` adapter for Claude
  Code CLI background sessions when Codex-native visible threads are not
  available. Always dry-run custom or uncertain commands first. Do not execute
  unless the user or project configuration explicitly authorizes external
  spawns.
- `serial_single_agent`: one agent runs Executive, Builder, Reviewer, and Ledger
  duties sequentially. Keep role boundaries explicit and record the same DB
  evidence. Do not choose this solely because workers do not inherit plugin
  context; agent packets carry that context explicitly.
- `manual_protocol`: human or test harness runs CLI commands directly to
  exercise the factory protocol.

Read `docs/runtime-modes.md` when explaining or changing runtime behavior.
Read `docs/dashboard.md` before presenting the local dashboard as a control
surface.

## Agent-CLI Startup Flow

When the user invokes the plugin from a generic agent CLI, do not ask the user
to manually run setup commands. Use this sequence:

1. Briefly infer or ask for the build objective and hard constraints.
2. Choose the work mode, topology, runtime mode, verification policy, and
   dashboard policy. Keep the prompt short; infer low-risk defaults.
3. Run `factory.py up --background` from the target project root. Use
   `--runtime-mode agent_cli_subagents` unless Codex-native mode is active or
   preflight selected an explicit adapter/session strategy. Use `--read-only`
   only if controls should be disabled. Do not use `--no-serve` for real
   factory startup; it is for tests only and leaves the dashboard URL without a
   running server.
4. Present the dashboard URL, run ID, project root, topology, runtime mode,
   control state, and top-level operator.
5. Pause and wait for the user to confirm readiness.
6. Begin factory operations only after confirmation, starting with status,
   doctor, and the first baton.

This startup flow is a compatibility layer for non-Codex environments. It does
not replace Codex-native thread orchestration when native Codex delegation is
available.

## Dashboard Control Loop

In agent-CLI dashboard workflows, dashboard messages are durable control
events, not guaranteed live terminal input. The lead agent must actively
consume them.

Before creating a baton, after every worker handoff, before acceptance, and at
least once per visible dashboard checkpoint:

```bash
python3 <plugin-root>/scripts/factory.py events list --type operator.message.requested --recent 20 --json
python3 <plugin-root>/scripts/factory.py events list --type baton.message.requested --recent 20 --json
python3 <plugin-root>/scripts/factory.py events list --type agent.message.requested --recent 20 --json
```

If a new dashboard message requests pause, scope change, status, review,
handoff, or cancellation, respond in chat and record the appropriate factory
event or baton transition before continuing. Do not silently ignore dashboard
control events.

## Capability Preflight

Before delegating to workers, establish the runtime capability profile without
running arbitrary external agent processes:

- native thread/sub-agent tools available;
- delegation mechanism and limits;
- worker workspace model: shared worktree, isolated worktree, forked workspace,
  or unknown;
- worker write permissions and shell-command permissions;
- worker skill/plugin/context inheritance;
- credential, secret, and environment inheritance;
- lead visibility into worker output, diffs, logs, and final packets;
- cancellation, timeout, pause, resume, and stale-worker recovery behavior;
- prompt, file, context, tool-call, and long-command limits.

If Claude Code CLI background sessions are available (`claude --bg`,
`claude agents --json`, attach/log/stop), prefer separate `claude-code`
sessions for substantial Builder/Reviewer work unless workspace or permission
risk makes that unsafe. If worker capability or ownership is ambiguous, pause
or use `serial_single_agent` until the ambiguity is resolved. Do not spawn
external agent CLI processes directly unless operating in an explicitly
configured adapter mode.

## Delegation Protocol

For every delegated worker:

1. Record or confirm the baton before sending work.
2. Give the worker role, baton id, objective, scope, non-goals, allowed areas,
   restricted areas, hard invariants, required checks, and handoff schema. Use
   `factory.py agent packet` when the runtime needs a portable delegation
   prompt.
3. State whether the worker may edit files, run commands, and record CLI
   evidence directly.
4. Require compact handoff output: files, behavior, contracts, commands,
   passing checks, failing checks, skipped checks, risks, and recommendation.
5. If the worker cannot use the CLI safely, the Executive/Ledger records its
   returned evidence.
6. Do not assign a Reviewer to edit files unless explicitly authorized.
7. Do not accept a baton until verification and review evidence meet the
   selected acceptance tier.

For Claude Code CLI session-backed delegation, the lead may create visible
background workers with:

```bash
python3 <plugin-root>/scripts/factory.py agent spawn \
  --adapter claude-code \
  --role builder \
  --baton B-001 \
  --experimental
```

Then inspect and refresh session state with:

```bash
python3 <plugin-root>/scripts/factory.py agent session list --sync --json
python3 <plugin-root>/scripts/factory.py agent session logs <session-id>
```

Use `--claude-worktree` for isolated write-capable workers only when the merge
plan is clear. Dashboard messages to Claude sessions are durable DB requests;
attach to the Claude session for true live conversation.

## Work Modes

- `discovery`: inspect, map, and identify risks; no product edits unless asked.
- `prototype`: prove an experience quickly; hardening gaps are explicit.
- `safe_mvp`: ship the thinnest real vertical slice while preserving hard
  invariants.
- `velocity`: larger product-visible slices, focused checks, periodic full gates.
- `balanced`: normal feature work, focused checks plus build, targeted review.
- `strict`: smaller batons, deeper review, full gates for high-risk code.
- `release`: scope freeze, release gates, deployment readiness, final smoke.
- `recovery`: reconcile dirty state, stale actors, collisions, failed gates, or
  unclear ownership before new work.
- `maintenance`: small low-risk fixes with focused regression evidence.
- `migration`: staged schema/API/data/infra work with compatibility gates.
- `design_sprint`: UI/product iteration with screenshots and browser/mobile QA.

Read `references/configuration.md` when mode choice, topology, policy knobs, or
escalation behavior matters.

## Roles

- Principal Partner: user-facing strategic overseer for substantial factories.
  It may steer, pause, reconfigure, replace stale ledgers, and request recovery
  according to authority. It normally does not hold the write baton.
- Executive: owns scope, routing, acceptance, commits, product judgment, and
  quality bar.
- Ledger: owns durable state, baton queue, evidence, risks, and cleanup records.
  In `executive_as_ledger`, this is the Executive.
- Builder: owns one scoped implementation baton and hands off evidence.
- Reviewer: read-only by default; produces findings and recommendation.
- Manager/User Liaison: packages user side feedback into Executive Briefs.
- Watcher/Monitor: observes and reports; never edits.

## Baton Lifecycle

1. Prepare: record baton goal, tier, scope, non-goals, risk, required checks,
   owner, and escalation triggers.
2. Authorize: send a fresh baton after assignment is recorded.
3. Build: Builder edits only scoped files and runs required checks.
4. Handoff: Builder reports files, behavior, contracts, commands, skipped
   checks, risks, and next recommendation.
5. Review route: Executive/Ledger reviews directly or assigns a Reviewer.
6. Review package: Reviewer reports findings and recommendation without editing
   unless explicitly authorized.
7. Patch or accept: Executive patches narrow gaps, sends fixes back, accepts, or
   rejects. Do not broaden scope silently.
8. Record: durable status, evidence, residual risk, skipped checks, and review.
9. Commit: stage explicit intended files, guard generated files, commit accepted
   work, and push when credentials permit.
10. Cleanup: archive or ignore completed worker contexts only after evidence is
    captured and unresolved risk is closed.

For DB-backed factories, each lifecycle transition should use `agentic-factory`
records rather than prose-only notes.

## Acceptance And Verification

Acceptance tiers:

- `prototype`: behavior is demonstrable; hardening gaps are recorded.
- `integration`: behavior is wired into product with focused verification and no
  known blocking regressions.
- `release`: full gates, release-specific checks, security/deployment readiness,
  and user-facing QA are complete.

Verification levels:

- `smoke`: command starts, primary workflow loads, or narrow syntax check.
- `focused`: tests or checks covering changed behavior.
- `focused_plus_build`: focused checks plus package/app build.
- `full_gate`: repository's full test, lint, type, and build gate.
- `release_gate`: full gate plus release-specific checks and final smoke.

Treat green tests as evidence only after checking that they cover changed
behavior. Record skipped checks honestly.

## Risk Escalation

Fast modes do not override hard safety. Escalate verification and review when
touching auth, permissions, security, secrets, money movement, destructive or
irreversible actions, production data, migrations, public APIs, shared schemas,
compliance, ranking/scoring logic, external live services, background jobs,
webhooks, queues, or deployment infrastructure.

In `safe_mvp`, cut breadth, polish, secondary workflows, exhaustive docs, and
full gates first. Do not cut real behavior, explicit external-effect boundaries,
mutation gates, security, or focused proof that the core flow works.

## Stop, Resume, And Recovery

Stop requests are control-plane commands. They preempt new baton assignment and
must preserve enough state for clean resume.

Default stop mode is `drain_to_checkpoint`. Use `hard_stop` or
`emergency_stop` only for safety, security, destructive-action, or ownership
risk.

On stop, capture active roles, current baton, worktree status, latest accepted
commit, dirty files, commands/tests in progress, monitors changed, unresolved
risks, and resume recommendation.

On resume, read the latest stop packet, DB status if available, current git
state, active actors, and unresolved risks before waking any worker. If state is
dirty, commands are still running, ownership is unclear, or evidence is missing,
switch to `recovery` first.

## Concurrency

Default to one active writer per worktree. Parallel read-only reviewers may
inspect committed code, diffs, screenshots, test output, architecture, security,
performance, or UI quality. Parallel implementation requires separate worktrees,
owners, scopes, merge order, conflict policy, and reconciliation gate.

Watchers and monitors never edit files.

When agent CLI sub-agents share a worktree, treat them as one-writer-at-a-time
participants under the same lock discipline. When workers run in forked or
isolated workspaces, require an explicit merge and reconciliation plan before
acceptance.

## Operating Rules

- Preserve user changes; never revert unknown work unless explicitly asked.
- Prefer repository patterns and existing tooling.
- Keep builders scoped and handoffs compact.
- Keep ledgers useful and evidence-based.
- Prefer product-visible vertical slices when the selected mode favors velocity.
- Keep hard invariants explicit in every baton.
- Keep Codex-native orchestration first when available; use other runtimes as
  compatibility modes.
- Treat `factory.py agent spawn` as explicit and opt-in. Prefer first-class
  session-backed adapters such as `claude-code` when they are safer than a
  single serial context; prefer packets without spawning when runtime safety is
  unclear.
- Treat `factory.py dashboard serve` as an optional visibility/control plane
  for non-Codex or adapter-heavy workflows, not a replacement for Codex app
  orchestration.
- In agent-CLI dashboard workflows, prefer `factory.py up --background` over
  making the user manually initialize state and start the dashboard.
- If push/auth fails, keep local commits and record remote status.
- If a design, browser, document, spreadsheet, GitHub, or other domain skill is
  explicitly named, use that skill for the relevant work.

## References

- `references/configuration.md`: mode presets, topology, role, verification,
  stop/resume, cleanup, permission, and escalation knobs.
- `references/templates.md`: concise factory config, baton, handoff, review,
  decision, stop, resume, and recovery packet templates.
- `../../docs/runtime-modes.md`: public runtime mode contract and delegation
  boundaries.
- `../../docs/agent-packets.md`: portable packet generation and generic CLI
  delegation flow.
- `../../docs/agent-adapters.md`: session/process adapter safety contract.
