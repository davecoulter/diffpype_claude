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

### Directory References
*   **Product Requirements:** Refer to `docs/prd.md` for overarching workflows.
*   **Architecture & Design:** Refer to numbered files in `docs/architecture/` (e.g., `01_...`) for stage-by-stage design and prompting.
*   **Claude Skills:** Refer to `.claude/skills/` (or `.claude/rules/`) for repeatable execution scripts.

### Clarifications & Logs
*(Claude will append a running log of global architecture decisions and ask clarifying questions here.)*