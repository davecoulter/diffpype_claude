# 01: System Architecture & Component Interactions
**Version:** 0.8
**Date:** 2026-06-30

### Preamble
This document dictates the technical implementation, component wiring, and strict API boundaries for the Diffpype system. It defines *how* the workflows in `docs/prd.md` will be executed using the tech stack mandated by `CLAUDE.md`. 

##### System Components & Boundaries
The system is divided into rigidly isolated layers to enforce testability and scalability, utilizing a Shared Service Layer pattern:
*   **Shared Service Layer:** The core Python modules (e.g., `src/services/`) that house all business logic. This layer accepts database sessions via dependency injection, mutates database state, generates S3 pre-signed URLs, and dispatches Celery DAGs. 
*   **API Boundary (FastAPI):** Acts as the thin HTTP entry point for the React Web UI. It uses Pydantic for strict I/O validation, but contains zero business logic, strictly delegating execution to the Shared Service Layer.
*   **CLI Boundary (diffpype-manage):** Acts as the direct terminal entry point for DevOps, database seeding, and administrative tasks. Like the API, it parses inputs and delegates execution to the Shared Service Layer.
*   **Task Orchestration (Celery):** Handles all asynchronous and long-running business logic. Workflows are constructed dynamically at runtime using native Celery Canvas primitives (groups, chains, chords).
*   **Data Persistence (PostgreSQL + SQLAlchemy):** The central system of record for domain entities. Structured relational data is stored here. Spatial data utilizes Q3C and HealpixAlchemy.
*   **Transient State & Queue (Redis):** Acts as the Celery message broker and result backend. Stores transient job progress, elapsed times, and stack traces for failed jobs.
*   **Queue Monitoring (Flower):** A lightweight web dashboard connected to Redis, used strictly for system administration and real-time visualization of the Celery task queue.
*   **Blob Storage (S3-Compatible):** The sole storage layer for all interstitial files (FITS images, catalogs). Configured dynamically via Docker environment variables.
*   **Frontend (React):** A thin visualization layer utilizing unidirectional state flow. Features a traffic-light status grid. Integrates fitsmap for low-latency image visualization by fetching assets directly from S3 via pre-signed URLs.

##### API Boundary Philosophy (Entity Separation)
Diffpype strictly separates API Boundary models (Pydantic) from Data Entity models (SQLAlchemy). ORM objects must never be exposed directly to or populated directly from the API router. This deliberate separation prevents mass-assignment security vulnerabilities, stops internal database state from leaking to the frontend, and allows the SQLAlchemy models to utilize complex low-level extensions (like `Q3C` spatial indexing and `healpix-alchemy`) without conflicting with serialization logic.


### S3 Execution & Storage Optimization Strategy
To minimize the storage footprint while preserving a stateless, cloud-native architecture, Diffpype relies on database-driven logical mapping rather than binary duplication.
*   **Logical Symlinks:** If a pipeline operation changes a file's state or naming convention without altering the binary pixel data, the worker does not duplicate the object in S3. Instead, FastAPI/Celery creates a new database entity that points to the existing S3 key.
*   **Ephemeral Worker I/O & Memory Management:** To prevent Out-Of-Memory (OOM) crashes on large mosaicing operations, workers do not stream heavy arrays directly into memory. Workers download required S3 objects to an ephemeral local container volume (`/scratch`). Algorithms process the files from this local disk utilizing memory-mapping or chunked lazy-loading. Genuine new binaries are uploaded back to S3, and the local scratch space is immediately wiped.
*   **Frontend File Serving (Pre-signed URLs):** FastAPI never serves heavy binary files directly to the React frontend. When the UI requests an image for `fitsmap`, FastAPI generates a temporary, pre-signed S3 URL. The React client uses this URL to download the FITS file directly from the S3 bucket, bypassing the API entirely.

##### Deployment & Environment Strategy (3-Tier)
Diffpype utilizes a strict 3-tier environment strategy governed by GitHub Flow and automated CI/CD pipelines:
*   **Dev (Local):** An ephemeral Docker Compose sandbox. Developers can freely mutate data, wipe volumes, and rebuild using `diffpype-manage reset-db` and database seeding.
*   **Test (Remote Staging):** A remote environment tracking the `main` branch. When a Pull Request is merged, CI/CD automatically builds and pushes images tagged as `:main` to the GitHub Container Registry (`ghcr.io`) for this environment to pull. To ensure realistic testing, this database is periodically hydrated with backups from the Production environment.
*   **Prod (Remote):** The live production system. It strictly tracks formal Git Tags (e.g., `v1.0.0`). Merges to `main` do *not* trigger production deployments. A production release is triggered manually, deploying the immutable, tagged `ghcr.io` images.

### Worker Routing & Hardware Constraints
Because tasks vary wildly in their computational and environmental needs, Celery tasks are explicitly routed to specialized queues. This allows specific Docker worker containers to subscribe only to the jobs they are provisioned to handle:
*   `queue='light'`: For fast, low-memory operations (e.g., metadata updates, database associations).
*   `queue='heavy_memory'`: For large Level 3 mosaic drizzling operations requiring high RAM and disk caching.
*   `queue='gpu'`: For GPU-accelerated resources (e.g., difference imaging written in JAX).
*   `queue='external'`: For tasks requiring bulky external dependencies (e.g., the STScI JWST pipeline) that are isolated in their own specific container images.

### Database Schema Strategy: Configuration & Status
Diffpype explicitly avoids the EAV (Entity-Attribute-Value) anti-pattern and monolithic "Job" tracking tables.
*   **Step Definitions:** A strict relational `StepDefinition` table maps a pipeline action to its specific Celery task name **and its required execution queue** (e.g., `gpu` or `external`).
*   **Flexible Configurations:** A `JobConfiguration` table utilizes a Postgres `JSONB` column to store the exact keyword arguments and parameters used for a specific run.
*   **Entity-Centric Status:** The state of the system is tracked directly on the astrophysical outputs (e.g., `Lvl2Cal`, `Lvl3Mosaic`), which hold their own status bits.
*   **Queue Bridging:** Domain entities include a `job_configuration_id` and a `latest_job_id` (the Celery task ID) to bridge Postgres records to Redis transient state.

### DAG Construction & Dependency Gating (Celery Canvas)
Workflows are dynamically constructed at runtime using native Celery Canvas primitives to handle topological "symmetry breaking" (many files to single files).
*   **Parallel Execution (`celery.group`):** Dispatches single-image operations concurrently.
*   **Synchronization (`celery.chord`):** Gating mechanisms wrap a group of parallel operations and fire a downstream callback only when all prerequisite tasks report success.
*   **Sequential Execution (`celery.chain`):** Downstream single-file actions are linked sequentially.

### FastAPI & Celery Handoff (The Job Lifecycle)
1. **Submission:** React/CLI POSTs a request to FastAPI.
2. **Dispatch:** FastAPI writes the domain entities to Postgres, constructs the Celery DAG, dispatches it to the correct queues, and returns a `job_id`.
3. **Execution & Logging:** Celery workers execute the task. The `job_id` is injected into `structlog` to trace all distributed actions.
4. **Real-Time Monitoring:** React subscribes to a FastAPI WebSocket using the `job_id` to receive live status updates. 
5. **Failure & Reprocessing:** If a task fails (red status), React fetches the stack trace from Redis. If a user clicks "reprocess", React fetches the initial input parameters from Postgres to populate the retry modal.

### Prototype Integration Strategy
Code currently residing in the `prototype/` directory will be used as a logical reference. Logic from the prototype will be systematically extracted, wrapped in Pydantic data contracts, and rewritten as isolated, dependency-injected Celery tasks.

### Clarifications
*(Claude will use this section to pause and ask the human questions regarding implementation details before generating code.)*

### Logs
#### 2026-07-01
*   **Action:** Drafted v0.1 - v0.4 of System Architecture baseline, defining DB, Cache, and DAG strategies.
*   **Action:** Updated to v0.5. (Retracted POSIX file system approach).
*   **Action:** Updated to v0.6. Restored strict S3-compatible storage constraints. Added the S3 Execution & Storage Optimization Strategy.
*   **Action:** Updated to v0.7. Enforced disk-caching to an ephemeral `/scratch` volume and mandated memory-mapping/chunking for worker algorithms.
*   **Action:** Updated to v0.8. Added the Worker Routing & Hardware Constraints section to govern Celery queue distribution for GPU and external pipeline requirements.
*   **Action:** Updated to v0.9. Added Flower as a visualization for the Celery/Redis queue.
*   **Action:** Updated to v1.0. Transitioned to a Shared Service Layer architecture. Removed FastAPI as the sole entry point for the CLI, elevating the CLI to a first-class administrative tool that shares core business logic modules with the API.