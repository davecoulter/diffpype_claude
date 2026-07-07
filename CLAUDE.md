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
*   **Environment Variable Synchronization:** Whenever an environment variable is added, modified, or removed, the change must be perfectly synchronized across both `.env.example` and the local `.env` file. These two files must always be identical in their set of keys.
*   **Model Evaluation Phase:** Before executing the instructions in any architectural markdown file, Claude must first analyze the complexity of the request, recommend the optimal model for the task (e.g., Opus for complex architectural refactoring, Sonnet for standard coding, Haiku for simple documentation), and explicitly **pause for human authorization** before proceeding. Once the task is completed, Claude must remind the user to remind the user to revert to the standard model.
*   **Command Authorization Rule:** Claude is explicitly authorized to autonomously execute standard, non-destructive development commands (e.g., `uv sync`, `uv lock`, `pytest`, `docker compose build`, `docker compose up`, `docker compose down`) without pausing for human authorization. **Note:** Destructive commands that wipe data volumes (e.g., `docker compose down -v`) strictly require human authorization. 

##### Operational Gotchas & Checklists
*   **Docker State:** If a Celery worker's routing, queue topology, or task signature is changed, Claude must remind the user to run `docker compose restart worker_light worker_heavy` to clear stale memory.
*   **Bug Regression Tests:** If Claude fixes a bug, it must proactively write at least one specific unit test designed to catch that exact class of error in the future.
*   **Stuck Database States:** When modifying asynchronous tasks, always verify that database rows cannot be left in an orphaned `IN_PROCESS` state if the worker crashes.
*   **Transactions:** Any global or framework-level error handler that intercepts a crash to update a database status MUST explicitly call `db.rollback()` before attempting to write the failure state, preventing `PendingRollbackError` crashes.
*   **Database Migrations:** If Claude modifies the SQLAlchemy models in `src/db/models.py`, it must automatically generate the Alembic migration script using `--autogenerate`. Afterward, it must explicitly pause and remind the user to run `alembic upgrade head` (or the equivalent Docker command) to apply the changes to the live database before proceeding.
*   **Git Workflow:** The repository uses GitHub Flow. Direct pushes to `main` are forbidden. Claude must instruct the user to create a new feature branch (e.g., `feature/xyz`), commit changes there, and open a Pull Request against `main`.

### Directory References
*   **Product Requirements:** Refer to `docs/prd.md` for overarching workflows.
*   **Architecture & Design:** Refer to numbered files in `docs/architecture/` (e.g., `01_...`) for stage-by-stage design and prompting.
*   **Claude Skills:** Refer to `.claude/skills/` (or `.claude/rules/`) for repeatable execution scripts.

### Clarifications & Logs
*(Claude will append a running log of global architecture decisions and ask clarifying questions here.)*

###### 2026-07-02
*   **Action:** Added Model Evaluation Phase and Command Authorization Rule to Guardrails for Agentic Coding to optimize model usage and whitelist non-destructive commands.