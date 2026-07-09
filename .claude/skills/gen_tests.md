# Skill: Generate and Run Test Plan
**Trigger Command:** `genTests on [filename.md]`

**Action:**
Read `docs/architecture/[filename.md]`. Derive the complete test plan for this implementation. Then run it interactively, one step at a time — do not dump the full list and wait. Present each step, wait for the user to execute and report the result, then proceed.

---

## Phase 1 — CLI Verification

Present the following steps **as a group** (they are fast, sequential, and non-interactive). Tell the user to run them in order and report back with any failures.

Derive the exact commands from context:
- `git branch --show-current` — confirm on feature branch
- `docker compose build [services]` — only services whose code changed
- `docker compose up -d [services]` — recreate containers
- `docker compose exec api alembic upgrade head` — only if models changed; otherwise mark SKIP
- `docker compose exec api uv run pytest --cov=src --cov-fail-under=90 -q`
- Sphinx locally: `DATABASE_URL="postgresql+psycopg2://dummy:dummy@localhost/dummy" REDIS_URL="redis://localhost:6379/0" uv run sphinx-build -b html docs docs/_build/html -W`

Wait for the user to confirm all CLI steps pass before proceeding to Phase 2.
If any CLI step fails: diagnose, fix, and ask the user to re-run that step before continuing.

---

## Phase 2 — Application QA

Before presenting any steps, derive and count all QA steps from the arch doc. Label each step **QA Step X/N** so the user always knows their position and total remaining.

Present **one step at a time**. After each step, explicitly ask: "Did that work? What did you see?" Do not move to the next step until the user confirms the current one passes.

Derive QA steps from the arch doc sections. For each major behaviour:

**Rules for writing QA steps:**
- Before writing any QA step, verify that the full execution path for that behaviour exists (routes wired, services registered, queues configured, migrations applied, data seeded). If the path is not yet available, note it explicitly and skip the step rather than substituting a plausible-sounding but untestable verification.
- For any feature/behavior exposed via both the API and the `diffpype-manage` CLI (per CLAUDE.md's API/CLI Parity rule), include a live QA step exercising **both** boundaries — not just one. Do not assume API-path testing implicitly covers the CLI path; they delegate to the same service-layer function but may diverge in surrounding behavior (tracing, logging context, error surfacing) that isn't part of that shared function.
- Every failure path involving real infrastructure (DB, Redis, broker, filesystem) must have a concrete manual step — never skip these as "covered by unit tests"
- Specify the exact command to trigger the behaviour (prefer `docker compose exec worker celery ... call` to bypass service-layer validation for failure paths)
- Specify exactly where to look: Portainer container name and log event name, Flower tab and field, DBeaver table and column, browser status code
- Specify the exact observable outcome — what value, what event name, what state — that confirms success
- Specify what "wrong" looks like so the user can distinguish a pass from a silent failure

**Infrastructure failure paths require a live test with real failure injection:**
- DB connection failures: `docker compose stop db` before dispatching, `docker compose start db` after
- Redis failures: `docker compose stop redis` before dispatching, `docker compose start redis` after
- Worker crashes: `docker compose kill worker_light` mid-task, then `docker compose up -d worker_light`

---

## Logging

Any time a QA step reveals a bug that requires a code fix, append a dated entry to the `## Logs` section of the arch doc immediately after the fix is made — before moving to the next QA step. The entry must record: what the bug was, what triggered it, and what was changed to fix it. Do not batch log entries at the end; log each fix as it happens so the record is accurate even if the session is interrupted.

If a QA step passes cleanly with no fixes needed, no log entry is required for that step.

## Exit Condition

When every step in Phase 1 and Phase 2 has been confirmed by the user:

Output exactly:
> ✅ All CLI and Application QA steps verified. Ready for `genPR on [filename.md]`.
