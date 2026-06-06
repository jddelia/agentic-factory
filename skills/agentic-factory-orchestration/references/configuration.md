# Agentic Factory Orchestration Configuration

Use this reference when creating or changing a factory's operating culture.
Keep project-specific invariants in project docs or DB records, not in this
skill.

## Mode Presets

| Work mode | Baton size | Acceptance tier | Verification | Review | Role topology | Cleanup | Default stop | Best for |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `discovery` | micro | prototype | smoke | skim | lean_solo | manual | pause_new_work | repo mapping and risk discovery |
| `prototype` | vertical_slice | prototype | smoke/focused | targeted | standard | rolling_window | drain_to_checkpoint | fast end-to-end demos |
| `safe_mvp` | vertical_slice | integration | focused | targeted | reviewed | rolling_window | drain_to_checkpoint | thin real slices under hard invariants |
| `velocity` | vertical_slice | integration | focused_plus_build | targeted | reviewed | rolling_window | drain_to_checkpoint | rapid product progress |
| `balanced` | medium | integration | focused_plus_build | targeted | reviewed | rolling_window | drain_to_checkpoint | normal feature work |
| `strict` | small | integration/release | full_gate | full | reviewed | after_acceptance | drain_to_checkpoint | high-risk code and contracts |
| `release` | micro/small | release | release_gate | adversarial | enterprise | release_archive | release_freeze | final ship readiness |
| `recovery` | micro | integration | focused/full as needed | full | reviewed | manual | hard_stop | messy state and failed gates |
| `maintenance` | small | integration | focused | targeted | standard | rolling_window | drain_to_checkpoint | bug fixes and upkeep |
| `migration` | small | integration/release | full_gate | full | reviewed | after_acceptance | drain_to_checkpoint | schema, data, API, or infra transitions |
| `design_sprint` | medium/vertical_slice | prototype/integration | focused_plus_build | targeted | reviewed | rolling_window | drain_to_checkpoint | UI/UX iteration |

## Mode Selection

- Choose `balanced` for ordinary feature implementation.
- Choose `safe_mvp` when the user wants a working core flow quickly but still
  expects real behavior and protected invariants.
- Choose `velocity` when the user explicitly wants fast delivery or iteration.
- Choose `strict` for shared contracts, security-sensitive behavior,
  business-critical logic, or suspect prior quality.
- Choose `release` when preparing to deploy, merge, publish, or declare done.
- Choose `recovery` for collisions, stale actors, dirty worktrees, failing
  gates, unexpected changes, or unclear ownership.
- Choose `prototype` when the goal is learning or proving a concept.
- Choose `design_sprint` for visual/product surface work with screenshots or
  browser/mobile QA.

Ask for mode only when it is not obvious. Do not turn setup into a long
interview; infer the rest and record it as editable config.

## Core Knobs

Common fields:

```text
work_mode:
factory_topology: executive_as_ledger | separate_ledger | passive_fallback
role_topology: lean_solo | standard | reviewed | managed | enterprise
user_involvement: principal_partner | direct_executive | hands_off
feedback_handling: no_manager | feedback_manager | always_on_manager
target_outcome:
baton_size: micro | small | medium | vertical_slice
acceptance_tier: prototype | integration | release
verification_level: smoke | focused | focused_plus_build | full_gate | release_gate
full_gate_cadence: every_baton | every_n_batons | risk_triggered | release_only
concurrency_policy: single_writer | parallel_read_only_reviewers | parallel_worktrees
review_depth: skim | targeted | full | adversarial
handoff_detail: compact | standard | exhaustive
browser_qa_policy: none | smoke | screenshots | full | release
external_effect_policy: mock_only | explicit_operator | staging_allowed | production_requires_confirmation
thread_cleanup_policy: none | manual | after_acceptance | rolling_window | aggressive | release_archive
factory_stop_policy: enabled | manual_only | disabled
default_stop_mode: pause_new_work | drain_to_handoff | drain_to_checkpoint | release_freeze | hard_stop | emergency_stop
resume_policy: manual | resume_from_stop_packet | resume_requires_user
permission_profile: read_only | workspace_write | full_access | custom
sandbox_mode: read_only | workspace_write | full_access
approval_policy: always | on_request | on_failure | never
destructive_action_policy: forbid | confirm | allow_scoped
credential_policy: never_prompt | use_existing_only | prompt_if_present
capability_preflight: minimal | standard | full
```

`full_access` is a requested factory profile, not proof that the runtime granted
it. If the environment still prompts, record the mismatch and use blocker policy
instead of stalling silently.

## User Involvement

Use `principal_partner` for substantial or long-running factories unless the
user asks for direct or hands-off operation.

```text
user_involvement: principal_partner
feedback_handling: no_manager
principal_policy: user_thread
principal_authority: configure
principal_intervention_policy: can_supersede_ledger
principal_digest_cadence: checkpoint
principal_context_budget: standard
```

Add a Manager/User Liaison only when side feedback volume would otherwise
interrupt the Executive or Builder.

## Tool And Thread Policies

Default substantial-build settings:

```text
tool_call_budget_policy: bounded_reads
thread_read_policy: latest_only
active_actor_polling_policy: adaptive_backoff
active_builder_poll_interval: 3m
long_check_poll_interval: 5m
handoff_poll_interval: 60s
stale_ping_after: 10m_without_meaningful_progress
stale_reclaim_after: 20m_to_30m_policy_dependent
```

If an orchestration or thread tool call fails with schema/window limits, remove
optional fields, narrow the request, retry once, then ask the active
Executive/Ledger or Builder for a compact status packet. Do not treat tool
inspection failure as product failure.

## Safe MVP Contract

Safe cuts:

- one primary workflow instead of broad coverage;
- one or two reliable providers instead of broad integrations;
- focused tests and targeted browser QA instead of full release gates every
  baton;
- simple deterministic policy v0 instead of full scoring or recommendation;
- compact docs plus hardening backlog instead of exhaustive operator material.

Unsafe cuts:

- fake success or fixture data presented as real behavior;
- hidden external calls on page load, readiness, tests, jobs, or monitors;
- unredacted secrets, credential prompts, or uncontrolled production effects;
- irreversible writes or high-impact mutations without explicit gates;
- skipping focused proof that the MVP flow works.

## Escalation Triggers

Escalate verification and review for:

- auth, permissions, sessions, security, secrets, or encryption;
- payments, billing, trading, money movement, or irreversible user actions;
- production data writes, migrations, destructive commands, infra, or deploys;
- public API contracts, shared packages, data schemas, generated clients, SDKs;
- scoring, ranking, recommendation, policy, compliance, ML/eval, or safety
  logic;
- external live services, background jobs, schedulers, webhooks, queues, or
  provider calls.

When escalated, record why and which knobs changed.

## Cleanup Policy

Never archive active, blocked, unresolved, unreviewed, uncommitted, or open-risk
threads. Preserve Manager, Executive, Ledger, and any thread explicitly pinned
or marked for audit.

Allowed policies:

- `none`: never cleanup automatically.
- `manual`: suggest cleanup and wait for action.
- `after_acceptance`: archive completed Builder/Reviewer threads after accepted
  commit and ledger evidence.
- `rolling_window`: keep active roles plus the last N completed workers.
- `aggressive`: keep only active roles, pinned roles, and unresolved-risk
  threads.
- `release_archive`: archive completed workers after release acceptance.
