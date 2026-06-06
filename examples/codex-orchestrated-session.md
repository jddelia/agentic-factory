# Codex-Orchestrated Factory Session

This example shows the intended Agentic Factory flow in the Codex app. The
human asks Codex to run a factory; the lead Executive uses the orchestration
skill, delegates scoped work to role-specific workers when native runtime tools
are available, and records durable state through `factory.py`.

This is not a shell-only transcript. The shell commands shown below are the
state transitions emitted by agents during the run.

## Starting Request

```text
Run a DB-backed factory for this project and add focused coverage for
hello.greeting. Do not commit until the work is reviewed.
```

## 1. Executive Preflight

The Executive inspects the repository, git state, runtime capabilities, and
existing factory state before assigning work.

Example runtime decision:

```text
runtime_mode: codex_native
work_mode: balanced
factory_topology: executive_as_ledger
role_topology: reviewed
acceptance_tier: integration
verification_level: focused
concurrency_policy: single_writer
worker_workspace: shared worktree
review_route: read-only Reviewer worker after Builder handoff
```

The Executive initializes or inspects durable state:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" init \
  --mode balanced \
  --objective "Add focused coverage for hello.greeting"

python3 "$PLUGIN_ROOT/scripts/factory.py" status --compact
python3 "$PLUGIN_ROOT/scripts/factory.py" doctor
```

## 2. Executive Creates A Baton

The Executive records the baton before delegating work:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton create B-001 \
  --title "Add greeting helper coverage" \
  --owner "Builder" \
  --scope "Add focused coverage for hello.greeting" \
  --acceptance-tier integration \
  --verification-level focused
```

The baton becomes the worker contract:

```text
role: Builder
baton_id: B-001
objective: Add focused coverage for hello.greeting
scope: tests for greeting behavior only
non_goals: broad refactor, unrelated test cleanup, release packaging
allowed_files_or_areas: tests/, hello.py only if required for a failing test
restricted_files_or_areas: generated files, config files, unrelated modules
required_checks: python3 -m unittest discover -s tests -v
handoff_required: files changed, commands run, verification result, residual risk
```

## 3. Builder Worker Runs The Baton

The Executive gives the baton to a Builder worker through Codex-native
delegation. The Builder edits only the scoped files and runs the required
checks.

If the Builder has safe CLI access, it records verification directly:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" verify record \
  --baton B-001 \
  --command "python3 -m unittest discover -s tests -v" \
  --result pass \
  --summary "Focused greeting test passed"
```

Then the Builder records the handoff:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton handoff B-001 \
  --summary "Added focused greeting helper coverage" \
  --files "tests/test_hello.py" \
  --commands "python3 -m unittest discover -s tests -v" \
  --verification "unittest: pass" \
  --risks "No known blocking risks" \
  --next "Reviewer should inspect the test coverage and recommend acceptance"
```

If the runtime does not allow the worker to run the CLI, the Builder returns
the same handoff fields to the Executive or Ledger, which records them.

## 4. Executive Routes Review

The Executive inspects the handoff and assigns a read-only Reviewer worker when
the runtime supports it:

```text
role: Reviewer
baton_id: B-001
scope_to_review: tests/test_hello.py and changed behavior only
review_depth: targeted
must_check: coverage relevance, accidental broad scope, test reliability
do_not_edit: true
recommendation_required: accept | patch | reject | escalate
```

The Reviewer records the review packet, or returns it for the Executive/Ledger
to record:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status accepted \
  --summary "Focused test covers greeting behavior and no blocking issues were found"
```

If findings exist, the Reviewer records them as structured rows:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" review record \
  --baton B-001 \
  --reviewer "Reviewer" \
  --status patch_required \
  --summary "One narrow issue needs a patch" \
  --finding "P2|tests/test_hello.py|8|open|Add a punctuation assertion"
```

## 5. Executive Accepts Or Patches

The Executive accepts only after the configured tier is met. If review requires
a patch, the Executive sends a new narrow baton or asks the Builder to revise
within the original scope.

When accepted, the Executive stages explicit files and commits:

```bash
git add tests/test_hello.py
git commit -m "test: add greeting helper coverage"
COMMIT_SHA="$(git rev-parse --short HEAD)"
```

Then the Executive records acceptance:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" baton accept B-001 \
  --commit "$COMMIT_SHA" \
  --pushed-status local_only \
  --summary "Accepted after focused verification and targeted review"
```

## 6. Ledger Snapshot

The Executive or Ledger renders a human-readable snapshot when useful:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" render-ledger \
  --out docs/build_ledger.md \
  --recent 20
```

The database remains the source of truth. The markdown ledger is a rendered
view.

## 7. Inspection And Recovery

Before assigning the next baton, the Executive inspects current state:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" status --compact
python3 "$PLUGIN_ROOT/scripts/factory.py" baton show B-001
python3 "$PLUGIN_ROOT/scripts/factory.py" events list --recent 20
```

If worker ownership, dirty files, failed commands, or missing evidence are
unclear, the Executive switches to recovery mode before assigning more work.

## Non-Codex Approximation

In an agent CLI with sub-agent support, the lead agent follows the same flow but
uses that CLI's delegation mechanism instead of Codex-native threads. The lead
can generate portable packets for those workers:

```bash
python3 "$PLUGIN_ROOT/scripts/factory.py" agent packet \
  --role builder \
  --baton B-001

python3 "$PLUGIN_ROOT/scripts/factory.py" agent packet \
  --role reviewer \
  --baton B-001
```

In a CLI without sub-agents, the lead agent performs the Builder and Reviewer
roles serially and records the same durable evidence.

For a command-by-command protocol exercise, see
[`basic-factory/session.md`](basic-factory/session.md).
