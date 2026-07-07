##### 15: Stage 0 Final Polish & CI/CD
**Version:** 0.1

###### Preamble
This document outlines the final architectural cleanup of the Stage 0 "Walking Skeleton" before Stage 1 commences. It addresses configuration management, normalizes job provenance, and completes the automated CI/CD deployment pipelines.

###### 1. Type-Safe Configuration (`pydantic-settings`)
*   **Directive:** Transition application-level configurations out of raw `os.environ` reads to separate framework/app configs from Docker infrastructure configs.
*   **Behavior:** 
    *   Add `pydantic-settings` to `pyproject.toml`.
    *   Create a `src/core/config.py` module defining a `BaseSettings` class (e.g., `Settings`). It must read from the `.env` file but provide type validation and defaults (e.g., `LOG_LEVEL: str = "INFO"`).
    *   Refactor the codebase (like `logger.py` or database URL fetching) to use this `Settings` object where appropriate.

###### 2. Normalize Job Configurations (Provenance)
*   **Directive:** Domain entities must not be polluted with execution metadata or task queue arguments.
*   **Behavior:**
    *   In `src/db/models.py`, remove the `job_kwargs` shortcut from the domain entities. 
    *   Implement a distinct `JobConfiguration` table. This table must contain the `job_kwargs` (JSON) and an `execution_command` (String) column to store the exact shell commands executed by workers for local reproducibility.
    *   Update the `DummyImage` table to include a `job_configuration_id` integer column defined as a ForeignKey pointing to `JobConfiguration.id`. Setup the bidirectional SQLAlchemy `relationship()` between the two models.
    *   Generate the Alembic migration for these changes.

###### 3. Auto-Seeding the Database Reset
*   **Directive:** Ensure developers always have a functional sandbox after dropping their database.
*   **Behavior:** Modify `src/cli.py` so that `cmd_reset_db` automatically calls `cmd_seed_db` at the end of its execution.

###### 4. GitHub Container Registry (ghcr.io) Pipeline
*   **Directive:** Automate Docker image builds for the 3-Tier environment strategy.
*   **Behavior:** 
    *   Update `.github/workflows/ci.yml`. 
    *   Add a new job (dependent on the `test` job passing) that builds `api.Dockerfile` and `worker.Dockerfile` and pushes them to `ghcr.io`.
    *   **Tagging Strategy:** If the workflow is triggered by a push to `main`, tag the images as `:main` (for the remote Test environment). If triggered by a Git Tag (e.g., `v1.0`), tag the images with the exact semver tag (for the remote Prod environment).

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Type-Safe Config, Job Provenance Normalization, Auto-Seed Reset, & ghcr.io Pipeline
*   **§1 Type-Safe Configuration:** Added `pydantic-settings==2.5.2` (`uv lock` → 59 pkgs). Created `src/core/config.py` with a `Settings(BaseSettings)` class (`database_url`, `redis_url` required; `log_level: str = "INFO"` default) and a module-level `settings` singleton, sourced from env vars / `.env` with `extra="ignore"`. Refactored `src/db/session.py` (`settings.database_url`), `src/worker/celery_app.py` (`settings.redis_url`), and `src/core/logger.py` (`configure_logging` now defaults its level from `settings.log_level`). Added `LOG_LEVEL` to `.env`, `.env.example`, and the `api`/`worker_light`/`worker_heavy` environment blocks in `docker-compose.yml` (`${LOG_LEVEL:-INFO}`); `.env`/`.env.example` key sets verified identical per the sync rule.
*   **§2 Normalize Job Configurations (Provenance):** Removed the `job_kwargs` shortcut from `DummyImage`. Added a `JobConfiguration` model (`id`, `job_kwargs` JSON, `execution_command` String) and a nullable `job_configuration_id` ForeignKey on `DummyImage`, with a bidirectional `relationship()` (`DummyImage.job_configuration` ⇄ `JobConfiguration.dummy_images`). `src/services/job_service.dispatch_dummy_job` now builds a `JobConfiguration` (recording `execution_command = "diffpype-manage run-dummy --sleep {n}"` for local reproducibility) and links it to the image via the relationship (single `db.add(image)` cascades the config insert). Honors the API Boundary Philosophy — the Pydantic request models remain separate from these ORM entities.
*   **Migration (0003):** Generated via `alembic revision --autogenerate` against the live dev DB (correctly detected the new table, FK, and dropped column), then authored a cleaned `20260706_0003_add_job_configurations.py` with sequential `revision="0003"`/`down_revision="0002"` and an **explicit FK constraint name** (`fk_dummy_images_job_configuration_id`) — autogenerate left it `None`, which would have broken `downgrade`'s `drop_constraint`. Paused per the CLAUDE.md migration rule; user applied `alembic upgrade head` → dev DB at `0003 (head)`. (Note: the api image had to be rebuilt first so the baked-in `migrations/` included 0003.)
*   **§3 Auto-Seeding Reset:** `cmd_reset_db` now calls `cmd_seed_db(args)` after `downgrade base` → `upgrade head`, so a freshly wiped sandbox is immediately usable.
*   **§4 ghcr.io Pipeline:** Added a `build-and-push` job to `.github/workflows/ci.yml` (`needs: test`, `if: github.event_name == 'push'`, `permissions: packages: write`). A matrix builds `docker/api.Dockerfile` and `docker/worker.Dockerfile` and pushes to `ghcr.io/${{ github.repository }}-{api,worker}` using `docker/metadata-action` — `type=raw,value=main` when on `refs/heads/main` (Test tier) and `type=semver,pattern={{version}}` on Git tags (Prod tier). `on.push` extended with `tags: ["v*.*.*"]`.
*   **Tests:** Integration tests replaced the `job_kwargs` cases with `JobConfiguration` round-trip + bidirectional-relationship + nullable-FK cases. Service tests now assert config lands on `image.job_configuration.job_kwargs` and verify `execution_command`. CLI tests updated so `reset-db` asserts the `downgrade → upgrade → seed` ordering and the auto-seed call. Added `src.core.config` to `docs/index.rst` and `pydantic_settings` to `autodoc_mock_imports`. Every new class/function carries a single-sentence docstring per the mandate.
*   **Verification:** `alembic upgrade head` → `0003 (head)`. `pytest --cov=src --cov-fail-under=90` → **45 passed, 98.76% coverage** (all new modules at 100%). `sphinx-build … -W` → **build succeeded, 0 warnings**. Workers rebuilt/restarted for live consistency (final end-to-end smoke-test deferred — Docker Desktop was restarting).
*   **Git Workflow:** All changes made on `feature/stage0-polish`; to be merged via Pull Request against `main` per the GitHub Flow rule (no direct pushes to `main`).