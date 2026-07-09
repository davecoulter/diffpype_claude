##### 23: Observability & Distributed Tracing
**Version:** 0.4

###### Preamble
This document is Chunk D of the hardening sequence. It replaces the manual `correlation_id` context threading with a standard OpenTelemetry (OTel) distributed tracing implementation, instruments the application for Prometheus metrics, and spins up a local Jaeger container for trace visualization.

###### 1. OpenTelemetry Distributed Tracing & Correlation ID Migration
*   **Directive:** Adopt standard OpenTelemetry tracing across the FastAPI, SQLAlchemy, and Celery boundaries.
*   **Behavior:**
    *   In `src/core/logger.py` and `src/api/main.py`, retain the `X-Correlation-ID` response header and the `structlog` context variable. However, source the value from `trace.get_current_span().get_span_context().trace_id` (formatted as a 32-character hex string) instead of generating a manual UUID.
    *   Create `src/core/tracing.py` to house all OTel initialization: configure a `TracerProvider` with an `OTLPSpanExporter` and a `BatchSpanProcessor`. The `OTLPSpanExporter` reads `OTEL_EXPORTER_OTLP_ENDPOINT` natively from the environment per the OTel specification — do not add this field to the `Settings` class and do not pass an explicit endpoint argument to the exporter constructor. Then call `FastAPIInstrumentor`, `SQLAlchemyInstrumentor`, and `CeleryInstrumentor` from this module. Call this module's setup function from `src/api/main.py` at startup and from `src/worker/celery_app.py` at worker startup. Add `.. automodule:: src.core.tracing` to `docs/index.rst`.
    *   In `src/services/job_service.py` and `src/cli.py`, remove the manual context variable extraction and kwargs passing. Rely entirely on the OpenTelemetry Celery instrumentation to propagate the trace context automatically across the worker boundary.
    *   In `src/api/main.py`, add a Starlette exception-handler middleware to the `admin` sub-application to make sqladmin exceptions visible to structlog. Since sqladmin is mounted as a separate ASGI sub-app, exceptions raised inside its routes bypass FastAPI's `unhandled_exception_handler` and are invisible to both OTel error recording and structlog. Attach a middleware (or a custom exception handler via `admin.app.add_exception_handler(Exception, ...)`) that calls `get_logger().error("sqladmin_unhandled_exception", exc_info=exc)` and re-raises, so all sqladmin errors surface in the structured log stream.
*   **Testing:** 
    *   Add a unit test in `src/api/tests/test_main.py` verifying that the `X-Correlation-ID` response header matches the active OTel trace ID. Configure the test with an `InMemorySpanExporter` and a `SimpleSpanProcessor` attached to a fresh `TracerProvider` (set via `trace.set_tracer_provider()`). Make a `TestClient` request, then retrieve the exported span's `trace_id` (formatted as a 32-character lowercase hex string via `format(span.context.trace_id, "032x")`), and assert it equals the `X-Correlation-ID` header value. Restore the original tracer provider in teardown.
    *   Add a unit test in `src/api/tests/test_main.py` for the sqladmin exception handler. Do not route through sqladmin's auto-generated views — instead, extract the registered exception handler function and invoke it directly with a mock request and a fake exception. Assert that `get_logger().error` was called with the event name `"sqladmin_unhandled_exception"` and that the exception is re-raised.
*   **Breaking Changes:** **Task Signature Changes.** Removing the manual `correlation_id` passing means the signatures for `sleep_and_update_status` and `execute_cli_tool` in `src/worker/tasks.py` must drop the `correlation_id` keyword argument. Any existing tests mocking or calling these `.delay()` or `.apply_async()` methods must be updated to remove the kwarg.
*   **Compliance:** Because we are modifying task signatures, remind the user to run `docker compose restart worker_light worker_heavy` after deployment to clear stale task definitions.

###### 2. Prometheus Metrics
*   **Directive:** Expose application metrics (request duration, counts) for scraping.
*   **Behavior:**
    *   Instrument the FastAPI application using `starlette-exporter` to expose a `/metrics` endpoint.
*   **Testing:** Add a test in `src/api/tests/test_main.py` asserting that a `GET /metrics` request returns an HTTP 200 and contains Prometheus-formatted text.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 3. Local Jaeger Infrastructure
*   **Directive:** Provide a local UI for visualizing distributed traces.
*   **Behavior:**
    *   Update `docker-compose.yml` to include a new `jaeger` service using the `jaegertracing/all-in-one:latest` image.
    *   Expose the Jaeger UI on the host using the `JAEGER_UI_PORT` environment variable.
    *   Update the `api` and `worker` services in `docker-compose.yml` to set the standard `OTEL_EXPORTER_OTLP_ENDPOINT` pointing to the new Jaeger container.

###### 4. Environment Variables
*   **Directive:** Ensure all new configurations are tracked and synchronized.
*   **Note:** `.env.example` and `.env` must remain identical in their set of keys.

| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `JAEGER_UI_PORT` | int | `16686` | The port exposed to the host for the Jaeger tracing dashboard. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | str | `"http://jaeger:4317"` | The endpoint where OpenTelemetry traces are sent. |

###### 5. Dependencies & Packages
*   **Directive:** Pin and install all observability dependencies.
*   **Packages:** Add the following to `pyproject.toml`:
    *   `opentelemetry-sdk==1.27.0`
    *   `opentelemetry-instrumentation-fastapi==0.48b0`
    *   `opentelemetry-instrumentation-sqlalchemy==0.48b0`
    *   `opentelemetry-instrumentation-celery==0.48b0`
    *   `opentelemetry-exporter-otlp-proto-grpc==1.27.0`
    *   `prometheus-client==0.21.0`
    *   `starlette-exporter==0.23.0`
*   **Mocking:** `starlette-exporter` or the `opentelemetry-instrumentation-*` packages may use class-level decorators or kwargs that fail the Sphinx build. If Sphinx import errors occur, add them to `autodoc_mock_imports` in `docs/conf.py`.

###### 6. CLAUDE.md Compliance
*   **Toctree Registration:** Add `23_observability` to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted architecture files as orphans and fails the CI `-W` build.

###### Logs

###### 2026-07-09 — Implementation (Claude Opus 4.8)
*   **§1 OTel tracing:** Created `src/core/tracing.py` with an idempotent `setup_tracing(app, engine)` that installs a `TracerProvider`, attaches a `BatchSpanProcessor(OTLPSpanExporter())` only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (keeping tests/local free of background gRPC export), and calls `SQLAlchemyInstrumentor`, `CeleryInstrumentor`, and `FastAPIInstrumentor`. Wired into `src/api/main.py` (after router/middleware assembly) and `src/worker/celery_app.py`. `src/core/logger.py` now injects the active span's trace ID (32-char hex) as `correlation_id` on every log event via a structlog processor, replacing the manual UUID. The API middleware sources `X-Correlation-ID` from the active span. Removed manual `correlation_id` extraction/passing from `job_service.py` and `cli.py`, and dropped the `correlation_id` kwarg from `sleep_and_update_status` and `execute_cli_tool`. Added the sqladmin exception handler on the `admin.admin` sub-app.
*   **§2 Prometheus:** Added `PrometheusMiddleware` + `/metrics` route via `starlette-exporter`.
*   **§3 Jaeger:** Added `jaeger` service (`jaegertracing/all-in-one:latest`, `COLLECTOR_OTLP_ENABLED=true`) and `OTEL_EXPORTER_OTLP_ENDPOINT` on `api`, `worker_light`, `worker_heavy`.
*   **Tests:** 115 pass; new-code coverage 100% (`tracing.py`, `logger.py`, `main.py`); overall 98.4%. Sphinx `-W` clean.

###### 2026-07-09 — Deviations & fixes discovered during implementation

*   **Deviation — test attaches InMemorySpanExporter to the active provider, not a fresh one.** The doc's §1 test guidance specified a fresh `TracerProvider` set via `trace.set_tracer_provider()`. In practice the OTel global provider is a write-once singleton: `main.py` sets it at import (before the test body runs), so a later `set_tracer_provider()` is ignored with a warning. The test in `test_main.py` instead attaches a `SimpleSpanProcessor(InMemorySpanExporter())` to the provider the app already uses, which reliably captures the request's server span. Same intent, working mechanism.

*   **Deviation — sqladmin handler registered on `admin.admin`, not `admin.app`.** The doc's example referenced `admin.app.add_exception_handler`. Inspection of sqladmin 0.18 showed `admin.app` is the *parent* FastAPI app while `admin.admin` is the mounted sub-app whose routes need the handler. Registered on `admin.admin`.

*   **Bug — `pkg_resources` missing after dependency sync.** `opentelemetry-instrumentation==0.48b0` imports `pkg_resources`, which setuptools removed in v81+. The resolver pulled setuptools 83, so every instrumentor failed to import with `ModuleNotFoundError: No module named 'pkg_resources'`. Discovered by an import smoke-test before writing code. Fixed by pinning `setuptools<81` in `pyproject.toml` (resolves to 80.10.2) and suppressing the resulting `pkg_resources is deprecated` UserWarning in the pytest `filterwarnings`.

*   **Bug — Sphinx theme silently pruned by `uv sync --all-groups`.** `sphinx-rtd-theme` and `sphinxcontrib-jquery` were present in the venv but never declared as dependencies, so `uv sync --all-groups` pruned them, which would have broken the `-W` build (`conf.py` sets `html_theme = "sphinx_rtd_theme"`). Discovered when the sync output showed them being uninstalled. Fixed by declaring `sphinx-rtd-theme==3.0.2` in the `test` dependency group so the docs toolchain is reproducible.

###### 2026-07-09 — stratSesh follow-up cleanups

*   **Silent no-export made observable.** `setup_tracing` now logs `tracing_configured` (with the endpoint) when an OTLP exporter is attached, and `tracing_configured_without_exporter` (warning) when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset — so a misconfigured prod environment that creates spans but exports nothing is no longer silent. Covered by assertions in `test_tracing.py` (both branches).
*   **Dead `correlation_id` handling removed from `on_failure`.** `DiffpypeTask.on_failure` no longer reads `kwargs.get("correlation_id")` or calls `bind_contextvars` — the new dispatch path never puts a correlation ID in kwargs, and the structlog trace processor supplies it from the active span. Removed the now-unused `structlog.contextvars` import and simplified the corresponding `test_base_task.py` case to pass `{}` for kwargs.

###### 2026-07-09 — CLI-path trace propagation verified live

*   Ran `docker compose exec api diffpype-manage run-dummy --sleep 3` and inspected the resulting trace in Jaeger to confirm §1's requirement — "rely entirely on OpenTelemetry Celery instrumentation to propagate the trace context automatically across the worker boundary" — holds for the CLI dispatch path, not just the API path (which is all prior QA had exercised).
*   **Confirmed working:** the `.delay()` call from `cmd_run_dummy` → `dispatch_dummy_job` correctly opens a producer span (`diffpype-api: apply_async/src.worker.tasks.sleep_and_update_status`) that the worker's consumer/run span nests under, forming one coherent 2-service trace. The `correlation_id` in the worker's structured logs matched this trace's ID exactly, same as the API path.
*   **Gap identified, not fixed:** DB writes in `dispatch_dummy_job` that happen *before* `.delay()` (creating the `DummyImage`/`JobConfiguration` rows) are not part of this trace — they run with no active span, since nothing wraps the whole CLI command in a root span the way `FastAPIInstrumentor` wraps an HTTP request. Logged as a deferred, uncertain-value enhancement in `docs/prd.md`'s Observability & Monitoring Infrastructure section rather than fixed now.
*   **Process gap found:** this was the first live CLI-path verification across docs 21–23; `genTests` had only ever exercised the API/UI boundary in Phase 2, despite CLAUDE.md's API/CLI Parity guardrail. Fixed by adding a rule to `.claude/skills/gen_tests.md` requiring live QA of both boundaries for any API/CLI-parity feature going forward.

###### 2026-07-09 — Bug found while designing genTests QA

*   **Bug — API and worker spans indistinguishable in Jaeger.** Neither `src/core/tracing.py` nor `docker-compose.yml` set `OTEL_SERVICE_NAME`, so `TracerProvider`'s default `Resource` falls back to the generic `unknown_service:python` for every process. The API and both workers would all appear under the same service name in Jaeger's service dropdown, making it impossible to distinguish which spans came from which process — undermining a core purpose of this doc. Caught before presenting the distributed-trace QA step, per the "verify the execution path exists before writing a QA step" rule. Fixed by adding `OTEL_SERVICE_NAME: diffpype-api`, `diffpype-worker-light`, `diffpype-worker-heavy` to the respective services in `docker-compose.yml` (the OTel SDK reads this env var automatically; no code change needed). Runtime-only change — requires `docker compose up -d`, not a rebuild.

*   **Bug — Jaeger UI unusable: white-on-white text, only visible via select-all.** Discovered during QA Step 1 live verification. Root cause is in Jaeger's own frontend (not our code) — the `jaeger` service was pinned to `jaegertracing/all-in-one:latest`, a floating tag that can silently pull a newer image with UI regressions on every rebuild. Fixed by pinning to a specific known-stable tag, `jaegertracing/all-in-one:1.57`, in `docker-compose.yml`, both to eliminate the floating-tag reproducibility risk and as the most likely fix for a recent theme/contrast regression. Requires `docker compose up -d jaeger` (or `docker compose pull jaeger && docker compose up -d jaeger`) to take effect — not a rebuild, since it's a stock image, not one we build. **Verified fixed:** confirmed legible in both normal and Incognito windows after the pin took effect — §3's "provide a local UI for visualizing distributed traces" deliverable now holds.