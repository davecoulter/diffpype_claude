# CLAUDE.md - Diffpype Global Meta Rules

### Project Overview
Diffpype is a lightweight DAG worker/queue system designed to orchestrate distributed astronomical data reduction and ML tasks. This document establishes the absolute guardrails and workflows Claude must follow.

### Core Tech Stack Constraints
Claude may only suggest packages or write code that aligns with this strict baseline:
*   **Backend & API:** Python, FastAPI (with Pydantic validation).
*   **Task Orchestration:** Celery (using Canvas primitives for DAGs) with Redis/RabbitMQ.
*   **Database:** PostgreSQL with SQLAlchemy, native Q3C, and HealpixAlchemy.
*   **Storage:** S3-compatible object storage (payloads pass string keys, never raw binary).
*   **Frontend:** React (unidirectional state flow).
*   **Infrastructure:** Docker/Podman containerization, CI/CD via GitHub Actions (ghcr).

### Guardrails for Agentic Coding
*   **Strict Human-in-the-Loop:** Claude is forbidden from writing implementation code until the design and architecture (stored in `docs/architecture/`) are human-approved.
*   **Test-Driven Development (TDD):** Every business logic function must be paired with an isolated unit test module. Code updates are not complete until the test suite passes at 100%. All logic must be completely isolated using Dependency Injection (mocking S3, API, and DB inputs via `pytest-mock`).
*   **Containerized Isolation:** The workspace utilizes a local Dockerfile and docker-compose.yml to sandbox dependencies, preventing host environment mutations.
*   **Definition of Done:** All implementations require an explicit Verification Plan containing deterministic commands (e.g., linters, build checks, test runs) to define when a task is complete.
*   **Sphinx Documentation Mandate:** Any newly created Python business logic module must be added to `docs/index.rst` using the `.. automodule::` directive before the implementation is considered complete. The Sphinx build (`sphinx-build -b html docs docs/_build/html -W`) must pass with zero warnings. Furthermore, every class and function must include a single-sentence, human-readable docstring describing its intention so it is picked up by Sphinx.
*   **Infrastructure Diagram Sync:** Whenever a change adds, removes, or restructures a `docker-compose` service, alters a container's internal module layers, or changes a data-flow/monitoring connection between services, Claude must update `docs/diagrams/infrastructure_topology.md` in the same change — not as a follow-up. If no diagram-relevant change occurred, no update is needed.
*   **Dependency Documentation Parity:** Whenever a new package is added as a project dependency, Claude must verify it doesn't break `sphinx-build -W` (adding it to `autodoc_mock_imports` in `docs/conf.py` if any module importing it is autodoc'd) and, if Sphinx/RTD needs it directly (not just mocked), add it to `docs/sphinx_requirements.txt` — not just `pyproject.toml`. `docs/sphinx_requirements.txt` is a separately-maintained list consumed by Read the Docs; it does not automatically track `pyproject.toml`/`uv.lock`.
*   **Environment Variable Synchronization:** Whenever an environment variable is added, modified, or removed, the change must be perfectly synchronized across both `.env.example` and the local `.env` file. These two files must always be identical in their set of keys.
*   **Model Evaluation Phase:** Before executing the instructions in any architectural markdown file, Claude must first analyze the complexity of the request and output a model recommendation with rationale. Claude must then **STOP COMPLETELY** — no file reads, no code, no tool calls — and wait for explicit human authorization (e.g. "proceed", "engage") before taking any further action. This pause is non-negotiable even when the model choice is obvious. Once the task is completed, Claude must remind the user to revert to the standard model.
*   **Command Authorization Rule:** Claude is explicitly authorized to autonomously execute standard, non-destructive development commands (e.g., `uv sync --all-groups`, `uv lock`, `pytest`, `docker compose build`, `docker compose up`, `docker compose down`) without pausing for human authorization. **Note:** Destructive commands that wipe data volumes (e.g., `docker compose down -v`) strictly require human authorization. 
*   **Meta-Configuration Change Confirmation:** Before editing this file (`CLAUDE.md`), any file in `.claude/skills/`, `.claude/context/gemini_rules.md`, or `.claude/settings.local.json`, Claude must first propose the change in chat and wait for explicit user confirmation. These files govern how Claude and Gemini behave across every future session, so changes to them are never made silently as a side effect of other work — even when the change seems obviously correct. This does not apply when the user has directly dictated the exact change in the current message (no need to ask them to re-confirm their own instruction).
*   **API/CLI Parity:** Any feature, query, or mutation exposed via the FastAPI router must have a corresponding, fully functional command in the `diffpype-manage` CLI. Both boundaries must delegate to the exact same function in the Shared Service Layer.
*   **Command Aliases:** If the user types `runPrompt on [filename.md]`, immediately read `.claude/skills/run_arch.md` and execute the instructions defined there.

*   **Skill Registry:** Claude has the following repeatable skills in `.claude/skills/`. When the user types the trigger command, immediately read the corresponding file and follow it exactly.
    *   `assessPrompt on [filename.md]` → `assess_arch.md`: Pre-implementation review of a Gemini-drafted architecture doc. Iterates until all checklist items pass, then clears the doc for `runPrompt`.
    *   `runPrompt on [filename.md]` → `run_arch.md`: Full implementation execution with model evaluation pause, branch reminder, and post-implementation verification checklist.
    *   `genTests on [filename.md]` → `gen_tests.md`: Interactive CLI + Application QA session. Runs one step at a time, waits for user confirmation, diagnoses failures. Only exits when all steps pass. Must be completed before `genPR`.
    *   `genPR on [filename.md]` → `gen_pr.md`: Generates commit message, PR title, and PR body from git context + the architectural doc. Assumes `genTests` has been completed — generates with pre-checked boxes and verified outcomes.
    *   `stratSesh on [filename.md]` → `strat_sesh.md`: Structured briefing on structural changes, data flow changes, and code review highlights for a completed doc. Interactive drill-down — user chooses what to explore further.
    *   `logIssue <description>` → `log_issue.md`: Files a GitHub Issue (tech-debt/enhancement/bug) directly — no branch, commit, or PR. This is now the sole tech-debt tracking mechanism, including debt discovered mid-implementation on an active branch — `docs/tech_debt.md` was retired in favor of GitHub Issues labeled `tech-debt`.



##### Operational Gotchas & Checklists
*   **Docker State:** If a Celery worker's routing, queue topology, or task signature is changed, Claude must remind the user to run `docker compose restart worker_light worker_heavy` to clear stale memory.
*   **Bug Regression Tests:** If Claude fixes a bug, it must proactively write at least one specific unit test designed to catch that exact class of error in the future.
*   **Log Everything:** Any bug found and fixed at any phase — during `runPrompt` implementation, during `genTests` QA, or during ad-hoc debugging — must be logged as a dated entry in the `## Logs` section of the relevant architecture MD file immediately after the fix, not batched at the end. The entry must record what the bug was, what triggered its discovery, and what was changed.
*   **Pre-Commit Runs Locally, Not in Docker:** `pre-commit` requires a `.git` directory, which is never copied or mounted into the `api`/`worker` containers. Running it via `docker compose exec` fails with `FatalError: git failed`. Always run `uv run pre-commit run --all-files` on the host, exactly like Sphinx.
*   **Stuck Database States:** When modifying asynchronous tasks, always verify that database rows cannot be left in an orphaned `IN_PROCESS` state if the worker crashes.
*   **Transactions:** Any global or framework-level error handler that intercepts a crash to update a database status MUST explicitly call `db.rollback()` before attempting to write the failure state, preventing `PendingRollbackError` crashes.
*   **Database Migrations:** If Claude modifies the SQLAlchemy models in `src/db/models.py`, it must automatically generate the Alembic migration script using `--autogenerate`. Afterward, it must explicitly pause and remind the user to run `alembic upgrade head` (or the equivalent Docker command) to apply the changes to the live database before proceeding.
*   **Git Workflow:** The repository uses GitHub Flow. Direct pushes to `main` are forbidden. The feature branch must be created **before** writing the architecture document — the arch doc file itself is a tracked change, and if it is committed on `main` first, it pollutes the PR diff. Claude must remind the user to `git checkout -b feature/[slug]` before Gemini begins drafting and before any implementation code is written. Commit changes on the feature branch and open a Pull Request against `main`.
*   **Integration Test Isolation:** Any test that calls a function which opens its own `SessionLocal()` and commits (e.g. `seed_step_definitions`) bypasses the transactional rollback fixture in `conftest.py`. Committed rows persist across the entire test session. Two rules: (1) test fixtures that create shared data must use usernames/names that don't conflict with seeded data (e.g. `"testowner"`, not `"sysadmin"`); (2) any test that triggers an out-of-fixture commit must explicitly delete the committed rows at the end of the test using its own session + commit.
*   **Architecture Wiki Toctree:** Whenever a new architecture markdown file is created in `docs/architecture/`, it must be manually added to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted markdown files as orphans and fails the `-W` build. This is easy to forget because the file itself is complete — the omission only surfaces in CI.
*   **Sphinx autodoc_mock_imports for Framework Glue Modules:** Any internal module that defines classes using framework-style keyword arguments at class definition time (e.g. `class UserAdmin(ModelView, model=User)`) will cause a `TypeError` in the Sphinx autodoc import phase, even if the external package is already in `autodoc_mock_imports`. This is because Sphinx's mock object does not cleanly propagate `**kwargs` through Python's `__init_subclass__` machinery. The fix is to add the internal module itself (e.g. `src.api.admin`) to `autodoc_mock_imports` in `docs/conf.py`, which prevents its class bodies from ever executing during the Sphinx build. Such modules do not need a `.. automodule::` entry in `docs/index.rst`.
*   **PR Workflow:** Claude generates PR title and body as plain text only. Do not run `gh pr create` or push to remote without explicit instruction. The user opens PRs via the GitHub UI and manages branch pushes manually.
*   **uv sync Must Include All Groups:** Always run `uv sync --all-groups` rather than bare `uv sync`. The bare command silently strips the `test` dependency group (pytest, httpx, coverage, etc.) from the virtual environment. The CI workflow correctly uses `uv sync --frozen --group test`; local development requires `--all-groups`.



### Directory References
*   **Product Requirements:** Refer to `docs/prd.md` for overarching workflows.
*   **Architecture & Design:** Refer to numbered files in `docs/architecture/` (e.g., `01_...`) for stage-by-stage design and prompting.
*   **Technical Debt:** Tracked as GitHub Issues labeled `tech-debt` — workarounds, dependency pins, and known limitations to revisit later. File new items via the `logIssue` skill rather than a markdown file.
*   **Claude Skills:** Refer to `.claude/skills/` (or `.claude/rules/`) for repeatable execution scripts.
*   **Collaborative Scratch Space:** `collab_scratch/` is a git-ignored directory for handoff artifacts between the user and Claude (drafts, demo pages, one-off files) that shouldn't be version-controlled. Prefer it over ephemeral session-only temp directories whenever the user may want to revisit or reopen something later.

### Clarifications & Logs
*(Claude will append a running log of global architecture decisions and ask clarifying questions here.)*

###### 2026-07-02
*   **Action:** Added Model Evaluation Phase and Command Authorization Rule to Guardrails for Agentic Coding to optimize model usage and whitelist non-destructive commands.