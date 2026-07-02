##### 10: Infrastructure Hardening & CI/CD Enhancements
**Version:** 0.2

###### Preamble
This document establishes vital infrastructure refinements to prepare Diffpype for heavy astronomical workflows. It parameterizes Celery worker resources, establishes a minimum viable approach for diverse hardware queues, introduces local container monitoring, enforces strict documentation and test reporting in the CI/CD pipeline, and ensures environment variable synchronization.

###### 1. Celery Worker Resource Limits
*   **Directive:** Expose Celery concurrency and memory limits to the environment to prevent Out-Of-Memory (OOM) crashes without requiring image rebuilds.
*   **Behavior:** 
    * Update `docker/worker.Dockerfile`'s CMD to accept variables for concurrency (`-c`) and max memory per child (`--max-memory-per-child`).
    * Add Docker-level memory limits (`deploy.resources.limits.memory`) to the worker services in `docker-compose.yml`.

###### 2. Diverse Queues (Minimum Viable Approach)
*   **Directive:** Support separate routing for fast API tasks and heavy astronomical tasks using a single Dockerfile.
*   **Behavior:** Replace the single `worker` service in `docker-compose.yml` with two distinct services: `worker_light` and `worker_heavy`. Both will build from `docker/worker.Dockerfile`, but their compose `command:` overrides will assign them to listen to the `light` and `heavy_memory` queues respectively, utilizing different concurrency variables.

###### 3. Local Resource Monitoring (Portainer)
*   **Directive:** Provide a lightweight, web-based UI to monitor CPU and Memory utilization across all local containers.
*   **Behavior:** Add a Portainer service to `docker-compose.yml`. Mount the Docker socket (`/var/run/docker.sock:/var/run/docker.sock`) and expose it on a standard port (e.g., 9000).

###### 4. Strict Documentation Validation
*   **Directive:** Use the Sphinx documentation build as a strict integration test for the development process itself. 
*   **Behavior:** 
    * Update the global metadata rules (`CLAUDE.md`) to mandate that any newly created business logic module must be added to `docs/index.rst` using the `.. automodule::` directive.
    * Update the GitHub Actions workflow (`.github/workflows/ci.yml`) to run the Sphinx build with the `-W` flag. This ensures any documentation warnings (like missing docstrings or failed imports) trigger a fatal pipeline error.

###### 5. GitHub Actions Test UI Dashboard
*   **Directive:** Expose a clickable, visual dashboard for test results in GitHub Actions.
*   **Behavior:** Update the pytest command in `.github/workflows/ci.yml` to generate a JUnit XML report (`--junitxml=results.xml`). Add a subsequent GitHub Action step (such as `EnricoMi/publish-unit-test-result-action`) to parse this file and generate a UI report on the PR/Commit page.

###### 6. Environment Variable Synchronization
*   **Directive:** Prevent configuration drift between the active environment and the repository templates.
*   **Behavior:** 
    * Ensure the new Celery concurrency and memory variables from Section 1 are explicitly added to both `.env.example` and the local `.env` file.
    * Update the global metadata rules (`CLAUDE.md`) to mandate: *"Whenever an environment variable is added, modified, or removed, the change must be perfectly synchronized across both `.env.example` and the local `.env` file."*

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Worker Resource Limits, Queue Split, Portainer, CI Documentation Validation, & Env Sync
*   **Celery Worker Resource Limits (§1):** `docker/worker.Dockerfile` CMD changed from JSON-array to shell form (`["sh", "-c", "celery ... -Q ${CELERY_QUEUES:-light} -c ${CELERY_CONCURRENCY:-2} --max-memory-per-child=${CELERY_MAX_MEMORY_PER_CHILD:-200000}"]`) so that environment variables are expanded at container start time.
*   **Diverse Queues (§2):** Single `worker` service replaced with two services in `docker-compose.yml`. `worker_light` sets `CELERY_QUEUES=light`, `CELERY_CONCURRENCY=${CELERY_LIGHT_CONCURRENCY:-4}`, `CELERY_MAX_MEMORY_PER_CHILD=${CELERY_LIGHT_MAX_MEMORY_PER_CHILD:-200000}`, and `deploy.resources.limits.memory: ${WORKER_LIGHT_MEM_LIMIT:-512m}`. `worker_heavy` sets `CELERY_QUEUES=heavy_memory`, `CELERY_CONCURRENCY=${CELERY_HEAVY_CONCURRENCY:-1}`, `CELERY_MAX_MEMORY_PER_CHILD=${CELERY_HEAVY_MAX_MEMORY_PER_CHILD:-8000000}`, and memory limit `${WORKER_HEAVY_MEM_LIMIT:-8g}`. Both build from the same `docker/worker.Dockerfile`.
*   **Portainer (§3):** `portainer/portainer-ce:latest` added to `docker-compose.yml`, mounting `/var/run/docker.sock` and a named `portainer_data` volume; exposed on `${PORTAINER_PORT:-9000}`. Added `PORTAINER_PORT=9000` to `.env.example` and `.env`.
*   **Sphinx Documentation Validation (§4):** `docs/conf.py` updated to set dummy `DATABASE_URL` and `REDIS_URL` via `os.environ.setdefault` so modules with fail-fast env var reads don't crash during autodoc import. `docs/index.rst` updated to include `src.cli` under a new CLI section. CI workflow now installs Sphinx deps via `uv pip install -r docs/sphinx_requirements.txt` and runs `uv run sphinx-build -b html docs docs/_build/html -W` as a dedicated step — **build succeeded with zero warnings**. `CLAUDE.md` updated with a Sphinx Documentation Mandate: any new business logic module must be added to `docs/index.rst` before implementation is considered complete.
*   **Test UI Dashboard (§5):** `pytest` command in CI updated with `--junitxml=results.xml`. `EnricoMi/publish-unit-test-result-action@v2` step added (`if: always()`) to parse the XML and publish a visual dashboard to the PR/Commit page.
*   **Environment Variable Synchronization (§6):** `CELERY_LIGHT_CONCURRENCY`, `CELERY_LIGHT_MAX_MEMORY_PER_CHILD`, `WORKER_LIGHT_MEM_LIMIT`, `CELERY_HEAVY_CONCURRENCY`, `CELERY_HEAVY_MAX_MEMORY_PER_CHILD`, `WORKER_HEAVY_MEM_LIMIT`, and `PORTAINER_PORT` added to both `.env.example` and `.env`. `CLAUDE.md` updated with an Environment Variable Synchronization mandate requiring `.env.example` and `.env` key sets to always be identical.
*   **Verification:** `sphinx-build -b html docs docs/_build/html -W` → **build succeeded, 0 warnings**. `pytest --cov=src --cov-fail-under=90 --junitxml=results.xml` → **15 passed, 96.03% coverage**, `results.xml` generated.