# Diffpype Technical Debt & Deferred Fixes

### Preamble
This document tracks small workarounds, dependency pins, and known limitations that should be revisited later. It is distinct from `docs/prd.md` (deferred *product* features) and `CLAUDE.md` (agentic guardrails and workflow rules). Each entry should be actionable: what the item is, and the specific condition under which it can be resolved and removed.

### Open Items

#### Remove `setuptools<81` pin
*   **What:** `pyproject.toml` pins `setuptools<81` because `opentelemetry-instrumentation==0.48b0` imports `pkg_resources`, which setuptools removed starting in v81. Without the pin, all OTel instrumentors fail to import (`ModuleNotFoundError: No module named 'pkg_resources'`).
*   **Resolution condition:** Once the `opentelemetry-instrumentation-*` packages are upgraded past `0.48b0` to a version that no longer imports `pkg_resources`, remove the `setuptools<81` pin and the corresponding `ignore:pkg_resources is deprecated as an API:UserWarning` entry in `[tool.pytest.ini_options] filterwarnings`.
*   **Source:** `docs/architecture/23_observability.md`, added 2026-07-09.

#### Adopt React Router `v7_startTransition` future flag
*   **What:** React Router emits a future-flag warning in the browser console during manual UI testing, recommending `v7_startTransition` be enabled ahead of the v7 migration.
*   **Resolution condition:** One-liner opt-in — add `future: { v7_startTransition: true }` to the router config in `src/ui/`. Nothing is currently broken; the UI is fully functional without it.
*   **Source:** Surfaced during doc 20 manual UI testing, 2026-07-08. Originally logged in `CLAUDE.md`'s Clarifications; moved here 2026-07-09.

#### Unify CLI-triggered traces with an explicit root span
*   **What:** `diffpype-manage` CLI commands (e.g. `run-dummy`) don't wrap their pre/post-dispatch DB writes in a root span the way `FastAPIInstrumentor` automatically wraps HTTP requests. The Celery dispatch onward correctly forms one coherent trace (confirmed live); DB writes before `.delay()` do not join it.
*   **Resolution condition:** Wrap `cmd_run_dummy` (or `dispatch_dummy_job`) in an explicit `tracer.start_as_current_span(...)` if/when CLI-side observability parity with the API becomes a priority. Uncertain value — the core propagation requirement (trace context flows automatically from CLI-triggered dispatch through to the worker) already works without this.
*   **Source:** Verified live during doc 23 QA, 2026-07-09. Originally logged in `prd.md`'s Deferred/Future Scope; moved here 2026-07-09.

### Resolved Items
*(none yet)*

### Logs
#### 2026-07-09
*   **Action:** Created this document to track technical debt separately from product-scope deferrals (`prd.md`) and agentic guardrails (`CLAUDE.md`). Added the `setuptools<81` pin as the first tracked item.
*   **Action:** Ported two items previously scattered elsewhere: the React Router future-flag warning (moved from `CLAUDE.md`'s Clarifications) and the CLI root-span gap (moved from `prd.md`'s Deferred/Future Scope). Both are code-level gaps in already-shipped work, not unbuilt product features, so they fit this document's scope better than `prd.md`'s.
