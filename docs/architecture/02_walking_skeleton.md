# 02: Walking Skeleton (Stage 0)
**Version:** 0.1
**Date:** 2026-06-30

### Preamble
This document defines the "Walking Skeleton" (Stage 0) for the Diffpype system. The goal is to define the thinnest possible vertical slice of functionality to validate that all system components (Database, API, Queue, and UI) can communicate correctly. No complex astronomical logic or spatial indexing will be implemented in this stage.

### Goals
* Prove the Docker orchestration and container networking.
* Prove the FastAPI layer can accept a request and write to PostgreSQL.
* Prove FastAPI can dispatch a task to the Celery queue (via Redis) and return a `job_id`.
* Prove the React frontend can trigger this flow and display the resulting status.

### Deliverables & Scope

**1. Infrastructure (Docker Compose)**
* A single `docker-compose.yml` file that orchestrates:
  * `db`: PostgreSQL container.
  * `redis`: Redis container (message broker and result backend).
  * `api`: FastAPI container.
  * `worker`: Celery worker container.
  * `ui`: Minimal React/Vite container.
  * `flower`: Celery monitoring dashboard exposing port 5555 to the host.

**2. Minimal Database (SQLAlchemy)**
* A rudimentary SQLAlchemy setup connected to the `db` container.
* Two tables to prove relational mapping and status tracking:
  * `StepDefinition`: A table holding a single dummy row mapping to a test task.
  * `DummyImage`: A domain entity table with a simple `status` string column and a `latest_job_id` column.

**3. Primitive Job Routing (FastAPI & Celery)**
* **Celery:** A single dummy task (`sleep_and_update_status`) that sleeps for 5 seconds and updates the `DummyImage` status in Postgres to "Success".
* **FastAPI:** A single `POST /jobs/dummy` endpoint that:
  1. Creates a `DummyImage` row in Postgres with status "Running".
  2. Dispatches the dummy Celery task.
  3. Returns the `job_id` and the `DummyImage` ID to the client.
* **FastAPI:** A `GET /jobs/dummy/{image_id}` endpoint to poll the current status. *(Note: WebSockets are deferred to Stage 1 to keep this skeleton as thin as possible).*

**4. Primitive React UI**
* A barebones React page.
* A single "Run Dummy Job" button.
* A basic text or color-coded status indicator (Red/Yellow/Green) that polls the GET endpoint and updates when the 5-second Celery job completes.

### Clarifications
*(Claude will use this section to pause and ask the human questions regarding implementation details before generating code.)*

#### Resolved (2026-06-30)
1. **Code layout:** New code lives under the existing top-level `src/`, split into `src/api`, `src/worker`, `src/db` (shared SQLAlchemy models/session), and `src/ui`.
2. **Python tooling:** Plain `pip` with a `requirements.txt` (shared by the `api` and `worker` containers) — no Poetry/uv for this stage.
3. **Frontend tooling:** TypeScript + npm, scaffolded via Vite.
4. **Testing scope:** CLAUDE.md's TDD/DI mandate applies in full even at Stage 0 — the FastAPI endpoints and the Celery task are covered by isolated `pytest` unit tests with mocked DB sessions/Celery dispatch (`pytest-mock`), in addition to manual end-to-end verification via `docker compose up`.

Implementation defaults chosen without a question (consistent with "thinnest possible slice"): integer autoincrement primary keys (no UUIDs yet), tables created via `Base.metadata.create_all()` on startup rather than Alembic migrations (deferred to a later stage), and the `POST /jobs/dummy` endpoint dispatches the Celery task directly rather than dynamically resolving it from the `StepDefinition` row (dynamic DAG construction from `StepDefinition` is Stage 1+ scope) — the seeded `StepDefinition` row exists solely to prove the table/relational mapping per the stage goals.

#### Prompts
1. Read this document, `CLAUDE.md`, `prd.md`, and `01_system_architecture.md`. Review the goals and deliverables for the Stage 0 Walking Skeleton.
2. If you have any questions before beginning, ask them in the Clarifications section. Do not generate code yet.
3. Once clarifications are resolved, generate the `docker-compose.yml`, Dockerfiles, and the minimal Python/React code required to satisfy the deliverables. Log your work.

### Logs
#### 2026-06-30
*   **Action:** Drafted v0.1 of Walking Skeleton, scoping the absolute minimum infrastructure, database, queue, and UI deliverables to prove network topology.
*   **Action:** Resolved all implementation clarifications (code layout, Python tooling, frontend tooling, TDD scope) with human approval. See Clarifications section.
*   **Action:** Implemented Stage 0 Walking Skeleton. File tree:
    *   `src/db/` — SQLAlchemy models (`StepDefinition`, `DummyImage`), session factory, idempotent seed script.
    *   `src/api/` — FastAPI app with `POST /jobs/dummy` and `GET /jobs/dummy/{image_id}`; lifespan-based DB init.
    *   `src/worker/` — Celery app configured against Redis, `sleep_and_update_status` task routed to `queue=light`.
    *   `src/ui/` — Vite + React + TypeScript minimal app with "Run Dummy Job" button and Red/Yellow/Green polling status indicator.
    *   `docker/api.Dockerfile`, `docker/worker.Dockerfile`, `docker/ui.Dockerfile`
    *   `docker-compose.yml` — orchestrates `db`, `redis`, `api`, `worker`, `ui` with healthchecks and hot-reload volume mounts.
    *   `requirements.txt`, `pytest.ini`, `.env.example`
*   **Verification:** `docker compose up --build` — all five services started healthy. `pytest` (4 tests, 4 pass): 3 isolated FastAPI unit tests (mocked DB + mocked Celery dispatch), 1 Celery task unit test (mocked `time.sleep` + mocked `SessionLocal`). E2E curl: `POST /jobs/dummy` → status `Running` → after 5s → status `Success`. `GET /jobs/dummy/99999` → 404. UI served on port 5173 (HTTP 200). `StepDefinition` seed row confirmed in Postgres.
*   **Action:** Updated to v0.2. Added Flower as a visualization for the Celery/Redis queue.