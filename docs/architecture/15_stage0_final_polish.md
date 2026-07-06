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