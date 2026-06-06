# Agentic Factory Orchestration Templates

Adapt these templates to the repository and selected work mode. Keep them
compact in prompts; store exhaustive detail in project docs or Agentic Factory
DB records.

## Effective Config Summary

```text
mode/topology:
target/tier:
principal/user involvement:
feedback handling:
active roles:
model/reasoning by role:
permission profile:
tool-call/thread-read:
active polling:
allowed prefixes:
restricted prefixes:
verification cadence:
review routing:
cleanup:
stop/resume:
known blockers:
```

## Capability Preflight

```text
thread_tools_available:
known_thread_tool_limits:
automation_tools_available:
goal_tools_available:
git_write_allowed:
git_push_auth_available:
network_available:
browser_available:
package_manager_available:
test_commands_detected:
env_files_present:
required_secrets_present:
generated_file_guards:
dev_server_status:
blocker_decision:
```

## Baton

```text
baton_id:
owner:
role:
title:
objective:
scope:
non_goals:
acceptance_tier:
verification_level:
required_checks:
allowed_files_or_areas:
restricted_files_or_areas:
hard_invariants:
external_effect_policy:
destructive_action_policy:
handoff_required:
escalation_triggers:
```

## Handoff Bundle

```text
baton_id:
owner:
base_commit:
files_changed:
behavior_changed:
contracts_changed:
commands_run:
passing:
failing:
not_run_and_why:
risks:
residual_gaps:
next_recommended_step:
```

## Review Baton

```text
reviewer:
baton_id:
handoff_source:
scope_to_review:
review_depth:
must_check:
do_not_edit:
recommendation_required: accept | patch | reject | escalate
```

## Review Package

```text
baton_id:
reviewer:
status:
summary:
findings:
verification_observed:
recommendation:
required_fixes:
residual_risks:
```

Finding row:

```text
severity|file|line|status|summary
```

## Decision Packet

```text
baton_id:
decision: accepted | patch_required | rejected | escalated
acceptance_tier:
evidence:
skipped_checks:
residual_risk:
commit:
push_status:
next_baton:
```

## Stop Packet

```text
stop_mode:
requested_by:
reason:
active_roles:
current_baton:
worktree_status:
latest_accepted_commit:
dirty_files:
commands_in_progress:
latest_verification:
latest_review:
monitors_changed:
cleanup_deferred:
unresolved_risks:
resume_recommendation:
```

## Resume Packet

```text
resume_authority:
resume_mode:
source_stop_packet:
current_git_state:
current_factory_state:
actor_to_wake_or_replace:
fresh_baton_authority:
verification_to_rerun:
monitors_to_restore:
cleanup_still_pending:
recovery_required:
```

## Recovery Packet

```text
trigger:
current_state:
ambiguous_ownership:
dirty_files:
failed_or_missing_checks:
uncommitted_accepted_work:
stale_threads_or_monitors:
collision_risk:
repair_steps:
next_safe_baton:
```
