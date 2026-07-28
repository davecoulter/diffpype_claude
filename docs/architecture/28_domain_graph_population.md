##### 28: Domain Graph Population & Service Boundaries
**Version:** 0.3

###### Preamble
This document establishes the headless domain graph population logic (Ingest, Tiles, Epochs, Mosaics). It enforces strict API/CLI parity, encapsulates Pandas entirely within service functions, and separates complex HEALPix/clustering computation from synchronous database persistence. It establishes the Storage Service factory pattern and populates the many-to-many associations that connect the domain graph.

###### 1. Schema Additions (`Project.slug` & `IngestBatch`)
*   **Directive:** Provide stable storage paths via immutable project slugs and track async ingestion.
*   **Behavior:**
    *   **Project Slug:** Add a `slug` column (String, `unique=True`, `nullable=False`) to the `Project` model. When creating new projects, generate the slug via `python-slugify`; reject collisions with an HTTP 400.
    *   **IngestBatch Tracking:** Create an `IngestBatch` model (inheriting `TimestampMixin`) with `id`, `project_id` (ForeignKey), `s3_prefix` (String), `total_files` (Integer, default 0), `processed_files` (Integer, default 0), and `status` (Enum(`JobStatus`), default `JobStatus.PENDING`).
    *   **Migration Strategy (Hand-Authored):** Generate the migration using Alembic, but hand-edit it to handle the `Project.slug` backfill. Create the column as nullable, backfill existing rows by slugifying their names (auto-deduplicating collisions with a numeric suffix like `-2`, `-3`), and then alter the column to `nullable=False`.

###### 2. Storage Service Factory & Key Layout
*   **Directive:** Provide a common storage interface capable of swapping between S3 and local disk.
*   **Behavior:**
    *   Create `src/services/storage_service.py` defining a `StorageBackend` Protocol (or ABC).
    *   Implement `S3StorageService` (using `boto3`) and `LocalStorageService` (using standard `shutil`/`os`). `LocalStorageService` must auto-create the `LOCAL_STORAGE_ROOT` directory if it is missing.
    *   Create a factory `get_storage_service(config) -> StorageBackend` that switches based on the `STORAGE_BACKEND` environment variable.
    *   **Key Layout Conventions:** Raw FITS files reside at `raw/{base_filename}` (flat, project-agnostic). Derived pipeline products reside at `projects/{project_slug}/working/{...}`.

###### 3. Async Ingestion Service & Pipeline
*   **Directive:** Scan a storage directory and execute idempotent bulk upserts.
*   **Behavior:**
    *   Create `src/services/ingest_service.py` and Pydantic schema `IngestRequest(project_id, s3_prefix)`.
    *   **API/CLI Write:** `POST /api/v1/ingest` (CLI: `diffpype-manage ingest`) creates an `IngestBatch` row as `PENDING`, dispatches `run_ingest_batch`, and returns the ID.
    *   **API/CLI Read:** `GET /api/v1/ingest/{id}` (CLI: `diffpype-manage ingest-status --id <ID>`) returns the `IngestBatch` status and progress counts.
    *   **Worker:** The task fetches the manifest, updates `total_files`, parses headers into Pandas, bulk-upserts `Level2Image` and `Level2Calibration` for every row from the prefix, and updates `processed_files`.

###### 4. Tile Generation & Association
*   **Directive:** Isolate tessellation math and populate spatial associations.
*   **Behavior:**
    *   Create `src/services/tile_service.py`. Schemas: `TileCreate` (name, ra, decl, delta_ra, delta_decl, footprint as `list[tuple[int, int]] | None`), `TileTessellationRequest`.
    *   **Compute (API/CLI):** `POST /api/v1/tiles/tessellate` (CLI: `diffpype-manage tessellate-tiles`) ports `GenerateSkyTiles` to return a preview `list[TileCreate]`.
    *   **Persistence (API/CLI):** `POST /api/v1/tiles` (CLI: `diffpype-manage create-tiles`) synchronously bulk-inserts `Tile` rows.
    *   **Association:** During persistence, the service queries for all `Level2Calibration` rows where `footprint && tile.footprint` (using the GiST index) and populates `tile_level2_calibration_association`.

###### 5. Epoch Generation & Association
*   **Directive:** Isolate temporal clustering and populate temporal associations.
*   **Behavior:**
    *   Create `src/services/epoch_service.py`. Schemas: `EpochCreate`, `EpochClusterRequest`.
    *   **Compute (API/CLI):** `POST /api/v1/epochs/cluster` (CLI: `diffpype-manage cluster-epochs`) queries the DB for `Level2Calibration` records intersecting the `tile_id`/`band_id`, extracts MJDs, runs `CreateEpochsFromMJDs` (scipy/sklearn), and returns `list[EpochCreate]`.
    *   **Persistence (API/CLI):** `POST /api/v1/epochs` (CLI: `diffpype-manage create-epochs`) synchronously bulk-inserts `Epoch` rows.
    *   **Association:** During persistence, the service populates `epoch_level2_calibration_association` for all calibrations whose MJDs fall within the Epoch's `start_mjd` and `end_mjd`.

###### 6. Mosaic Orchestration (Footprints & Barycenters)
*   **Directive:** Establish the job-tracking entity for the drizzle pipeline and compute its spatial properties (Addresses #27).
*   **Behavior:**
    *   Create `src/services/mosaic_service.py`. Schema: `MosaicCreate`.
    *   **API/CLI Write:** `POST /api/v1/mosaics` (CLI: `diffpype-manage create-mosaic`) synchronously creates a `Level3Mosaic` with `status=PENDING` and dispatches `run_mosaic_drizzle`.
    *   **API/CLI Read:** `GET /api/v1/mosaics/{id}` (CLI: `diffpype-manage mosaic-status --id <ID>`) polls the mosaic status.
    *   **Spatial Computation:** The service looks up the constituent `Level2Calibration` rows via the M2M tables. It uses `Get_Unioned_MOC` to merge their footprints into the mosaic's `footprint`. It computes the `ra` and `decl` barycenter from this union and stores it on the `Level3Mosaic`.
    *   **Worker:** The `run_mosaic_drizzle` task sleeps and transitions to `COMPLETE` (real drizzle deferred).

###### 7. Dev Coordinator & Smoke Test
*   **Directive:** Provide a developer tool to orchestrate the end-to-end population of the graph.
*   **Behavior:**
    *   Add a `diffpype-manage populate-demo-project` CLI command. It sequentially invokes the Ingest, Tiles, Epochs, and Mosaics services.
    *   Tracked as Issue #31: Create a manual `scripts/smoke/` script to run against a live stack.

###### 8. Environment Variables
*   **Directive:** Ensure all configurations are synchronized.
*   **Note:** `.env.example` and `.env` must remain identical.
| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| STORAGE_BACKEND | str | "s3" | The storage backend to use (must be "s3" or "local"). |
| LOCAL_STORAGE_ROOT | str | "./data" | The host directory for local storage, auto-created if missing. |

###### 9. Dependencies & Packages
*   **Packages:** Add `python-slugify`, `scipy`, and `scikit-learn` to `pyproject.toml` (Pandas/Mocpy/Boto3 are already installed).
*   **Mocking:** Add `scipy` and `sklearn` to `autodoc_mock_imports` in `docs/conf.py`.

###### 10. Testing Mandates
*   **Associations:** Write explicit integration tests proving the M2M association logic correctly links Tiles (via spatial overlap) and Epochs (via MJD).
*   **Mosaic Math:** Write unit tests for `Get_Unioned_MOC` and the barycenter extraction (Issue #27).
*   **API Routes:** Every new FastAPI route must be tested for success (200), validation failure (422), and missing resources (404).
*   **Dumb Pipes:** The synchronous DB write functions (`create_tiles`, `create_epochs`) must be explicitly unit/integration tested independently of their compute functions.

###### 11. CLAUDE.md Compliance & Implementation Sequencing
*   **Implementation Sequencing:** Implement §1 (Migrations) and §2 (Storage Factory) first. Then §3 (Ingest). Then §4/§5 (Tiles & Epochs). Finally, §6/§7 (Mosaics & Coordinator).
*   **Documentation Registration:** Add the four new service modules to `docs/index.rst`. Add `28_domain_graph_population` to `docs/architecture/index.md`.

###### Logs

###### 2026-07-27
*   **Bug:** §4's tile/calibration association query cited "the Q3C/GiST index" for the `footprint && tile.footprint` overlap lookup. Q3C indexes `ra`/`decl` points (`q3c_ang2ipix`) and is unrelated to this query — only the GiST index on the `footprint` multirange column (`ix_tile_footprint_gist`, added in doc 27) backs `&&`. Left in, this risked an implementor reaching for Q3C functions on a query they don't apply to.
*   **Trigger:** Found during `assessPrompt` review of v0.2. Fixed directly (deterministic, no design judgment involved) by editing "Q3C/GiST" → "GiST". Reverted when v0.3 came back from a full Gemini regeneration that didn't carry the direct edit forward; reapplied identically during the v0.3 `assessPrompt` pass.

###### 2026-07-28 — `runPrompt` implementation
Full implementation of v0.3 on `feature/domain-graph-population`. All 11 sections built, tested (240 tests, 99.3% coverage), Sphinx `-W` build clean, `alembic check` shows zero drift, migrations 0009/0010 round-tripped downgrade→upgrade cleanly. Notable deviations and gaps found/filled during implementation, beyond straightforward execution of the doc:

*   **Project creation was never actually specified.** §1 says new projects "generate the slug via `python-slugify`; reject collisions with an HTTP 400," but no doc ever defined a Project-creation service, endpoint, or CLI command for this to live on. Added a minimal `src/services/project_service.py` (`create_project`, catching the DB `IntegrityError` on slug collision and re-raising `ValueError`), `POST /api/v1/projects`, and `diffpype-manage create-project` — the smallest addition that makes §1's own directive implementable, not a scope expansion.
*   **`pandas` and `astropy` were never real dependencies.** §9 claimed "Pandas/Mocpy/Boto3 are already installed" — true for mocpy/boto3, false for pandas (not present anywhere in `uv.lock`, even transitively). Added `pandas==3.0.5` as a direct dependency. `astropy` (needed for FITS header/WCS parsing, tile tessellation, MJD clustering) is already resolved transitively via `mocpy`, matching the existing precedent of `numpy` being used directly without its own top-level pin — not re-declared as a direct dependency, but added to `docs/conf.py`'s `autodoc_mock_imports` alongside `pandas`/`scipy`/`sklearn`/`slugify` since all are now directly imported.
*   **`MosaicCreate` was missing required model fields.** `Level3Mosaic.filename`/`target_plate_scale` are `NOT NULL`, but the doc's `MosaicCreate` only listed FK fields. Added `filename`/`target_plate_scale` to the schema and CLI/API surface — mechanical, no design judgment.
*   **Issue #27 (`Level3Mosaic` ra/decl barycenter) required a schema change the doc never mentioned.** §6 says the computed barycenter is "stored on the Level3Mosaic," but no `ra`/`decl` columns exist on that model and §1 never added them. Added migration 0010: nullable `ra`/`decl` columns + a Q3C index (matching Tile/Level2Image), consistent with issue #27's own acceptance criteria and the earlier decision (this session) to fold #27 into doc 28.
*   **Real correctness bug found and fixed before it shipped: epoch↔calibration association was unscoped by tile/band.** `Epoch` is modeled as "a temporal grouping... for a given Tile and Band," but the first draft of `_associate_epochs_with_calibrations_in_range` only filtered by `project_id` + MJD range — it would have linked calibrations from any tile or band whose MJD happened to overlap, silently corrupting the M2M associations a future mosaic/orchestrator step depends on. Caught while implementing `mosaic_service` (which consumes those associations) before any test was written against it. Fixed by joining through `tile_level2_calibration_association` and filtering `Level2Image.band_id`, mirroring `cluster_epochs`'s own scoping. Regression test added: `test_create_epochs_persists_and_associates_calibrations_in_mjd_range` now includes a same-MJD/wrong-tile calibration that must NOT be linked.
*   **`DummyImage` decommission — deferred, tracked separately.** Removing the Stage-0 scaffolding (superseded by `IngestBatch`) was raised mid-implementation; scoped out of this doc per explicit decision (needs its own architecture doc under the human-in-the-loop rule, and `DiffpypeTask.on_failure`'s hardcoded `DummyImage` status-write needs a real generalized replacement, not a bare deletion). Filed as GitHub issue #33.
*   **`minio-init` fiducial seed data was designed in conversation but never built in any doc.** §7's coordinator assumed a fiducial MinIO dataset that doesn't exist — no `minio-init` service, no seed FITS files anywhere in the repo. Per explicit decision, `populate-demo-project` takes real CLI arguments (`--s3-prefix`, `--ra`/`--decl`/`--radius-deg`, `--band-id`, `--instrument-id`, etc.) instead of a hardcoded fiducial path; its control flow (ingest → tiles → epochs → mosaic, polling both async steps to a terminal state) is fully implemented and tested. Filed as GitHub issue #34 — real astronomical FITS files are a data-acquisition task, not something fillable in code.
*   **New Celery tasks (`run_ingest_batch`, `run_mosaic_drizzle`) intentionally not built on `DiffpypeTask`.** That base's `on_failure` hardcodes a `DummyImage` status write by `args[0]` — reusing it here would silently no-op, or worse, incorrectly mark an unrelated `DummyImage` row `FAILED` if one happened to share the same integer id as the batch/mosaic. Both new tasks handle their own crash-safety instead (explicit `try/except`, `db.rollback()` before writing failure state per CLAUDE.md's Transactions rule, mark the correct entity `FAILED`, re-raise), routed to the `heavy_memory` queue.
*   **`StorageBackend` protocol gained a `list_prefix` method not in the original design.** §3 assumes ingest can "fetch the s3_prefix manifest," but no prior storage-service design (this session's or doc 27's) ever specified a manifest/listing method — only `upload_file`/`download_file` existed. Added `list_prefix(prefix) -> list[str]` to the protocol and both `S3StorageService` (paginated `list_objects_v2`) and `LocalStorageService` (`Path.rglob`), since ingest cannot function without it.

**Verification commands run:** `uv run pytest --cov=src --cov-fail-under=90` (240 passed, 99.3%), `uv run sphinx-build -b html docs docs/_build/html -W` (clean), `uv run pre-commit run --all-files` (ruff, ruff-format, mypy all clean after fixing 7 real mypy findings — `Sequence` vs `list` param variance, an untyped `[]` literal, a `np.histogram` `range` tuple-vs-list mismatch, and two possibly-`None` attribute accesses in the coordinator's polling helpers), `alembic check` (zero drift against live dev DB), `alembic downgrade 0008` → `alembic upgrade head` round trip (clean).

**Not yet done, reminders for the user:**
*   Run `docker compose restart worker_light worker_heavy` — Celery task routing/signatures changed (`run_ingest_batch`, `run_mosaic_drizzle` added to `task_routes`).
*   Run `docker compose build api worker_light worker_heavy` then `docker compose up -d` before relying on the containerized environment — new dependencies (`pandas`, `python-slugify`, `scipy`, `scikit-learn`) need to land in the built images. Migrations 0009/0010 are already applied to the shared dev DB from the host, so `docker compose exec api alembic upgrade head` will correctly no-op.
*   `genTests` has not run yet — this Logs entry covers implementation-time verification only.

###### 2026-07-28 — `genTests` bug: OOM-killed worker on a real ingest batch, orphaned `IngestBatch` row
*   **Bug:** `run_ingest_batch` downloaded every file in the batch into a temp directory before parsing any of them. Against a real ~20-file batch of real JWST FITS data, this blew through `WORKER_LIGHT_MEM_LIMIT`/`CELERY_LIGHT_MAX_MEMORY_PER_CHILD` (sized for the trivial Stage-0 dummy `sleep()` task, never revisited) and the container was OOM-killed outright (`Killed` in the logs, no traceback). Because a SIGKILL isn't a catchable Python exception, the task's own `except`/rollback/mark-`FAILED` crash handling never ran — `IngestBatch(id=5)` was left permanently stuck at `in_process` with no worker ever going to touch it again, a direct violation of CLAUDE.md's Stuck Database States guardrail. Celery's `task_acks_late`/`task_reject_on_worker_lost` did not redeliver the task after the worker restarted (confirmed: `updated_at` never advanced).
*   **Trigger:** Live QA against real fiducial FITS data (staged by the user at a bind-mounted host directory, `STORAGE_BACKEND=local`) — the first time `run_ingest_batch` had ever processed more than a zero-file prefix.
*   **Fix:** `run_ingest_batch` now streams one file at a time — download → parse → `os.remove` — instead of materializing the whole batch on disk before any work happens, and updates `IngestBatch.processed_files` + logs an `ingest_file_processed` event after each file, giving real incremental progress instead of a single all-or-nothing jump at the end. `run_ingest_batch`/`run_mosaic_drizzle` were also re-routed from `light` back to `heavy_memory`: real FITS/astropy work is memory-hungry even though it isn't GPU-bound, and `light`'s multi-child concurrency (`CELERY_LIGHT_CONCURRENCY=4`, all children sharing one container memory ceiling) made it a poor fit regardless of per-task tuning — `heavy` is redefined for now to mean "resource/memory intensive," not GPU-specific. The orphaned `IngestBatch(id=5)` row was corrected manually (`UPDATE ... SET status = 'failed'`) since no automated path could recover it after the fact. New CLAUDE.md guardrails added as a result: QA/Debugging Fix Confirmation (propose before applying a fix, always) and Streaming & Bounded Resource Use (batch-processing tasks must stream, never materialize a whole batch up front).
*   **Regression tests added:** `test_run_ingest_batch_parses_one_file_at_a_time`, `test_run_ingest_batch_increments_processed_files_progressively`, `test_run_ingest_batch_logs_progress_per_file`, `test_run_ingest_batch_removes_temp_file_after_each_file`, `test_run_ingest_batch_handles_zero_files_without_crashing` (`src/worker/tests/test_tasks.py`).

###### 2026-07-28 — `genTests` bug: instrument/band matching rejected every real file
*   **Bug:** Once the OOM fix above let a real ~20-file batch actually stream through, it still failed — `ValueError: Unknown instrument/band for files: [...all 20...]`. Two distinct causes: (1) `_resolve_reference_ids` matched `INSTRUME`/`FILTER` header values against seeded `Instrument`/`Band` names with an exact, case-sensitive string match — real JWST headers write `INSTRUME='NIRCAM'` (uppercase), while the seed data used mixed-case `"NIRCam"`, so every NIRCam file failed the lookup. (2) Independently, the real files' `FILTER='F115W'` wasn't seeded at all — the reference `Band` table only ever had two placeholder rows (`F150W`, `F277W`) from Stage 0, not a real filter list.
*   **Trigger:** Live QA re-dispatch of the real ingest batch immediately after the OOM fix (batch_id=6) — confirmed via a read-only header inspection (`astropy.io.fits.getheader`) before proposing any fix, per the newly-added QA/Debugging Fix Confirmation guardrail.
*   **Fix:** `_resolve_reference_ids` now matches case-insensitively (`.str.upper()` on both the DB names and the header values). `src/db/seed.py`'s `_SEED_BANDS` replaced the 2-filter placeholder with the complete standard NIRCam (wide/medium/narrow) + MIRI imaging filter set, so the next not-yet-seen real filter doesn't reproduce the same gap.
*   **Regression test added:** `test_resolve_reference_ids_matches_case_insensitively` (`src/services/tests/test_ingest_service.py`).

###### 2026-07-28 — `genTests` bug: `mosaic-status` CLI table unreadable, dumping raw MOC + bare FK ids
*   **Bug:** `cmd_mosaic_status` printed every `Level3Mosaic` column through the generic `_print_entity_table` helper, including the raw `footprint` `mocpy.MOC` object (tabulate falls back to its Python repr, which is enormous and not human-readable) and five bare foreign-key ids (`instrument_id`, `band_id`, `tile_id`, `epoch_id`, `project_id`, `job_configuration_id`) that aren't meaningful without a join. The command's actual purpose — "did my job finish" — was buried in noise.
*   **Trigger:** Live QA Step 9a against a real mosaic row.
*   **Fix:** `_print_entity_table` gained an optional `fields` parameter to restrict/order printed columns, and `cmd_mosaic_status` now passes `["id", "filename", "status", "ra", "decl", "created_at", "updated_at"]` — status-focused, using the already-computed barycenter (`ra`/`decl`, from issue #27) instead of the raw footprint. Separately, `_print_entity_table` also gained a generic `_format_moc_for_display` fallback (renders any `MOC` value as `MOC(<sky_fraction*41253 sq.deg>)`) as defense-in-depth for any other current or future table call that surfaces a MOC column and hasn't been curated — `mosaic-status` itself no longer hits this path at all since footprint isn't in its field list.
*   **Regression tests added:** `test_format_moc_for_display_reduces_moc_to_compact_sq_deg_string`, `test_format_moc_for_display_passes_through_non_moc_values`, `test_print_entity_table_restricts_and_orders_columns_when_fields_given`, plus updated `test_cmd_mosaic_status_prints_table_for_found_mosaic` to assert `footprint`/FK ids are absent from output (`src/api/tests/test_cli.py`).

###### 2026-07-28 — `genTests` follow-up: `GET /api/v1/mosaics/{id}` also carried the same footprint fat
*   **Bug:** After the CLI table fix above, live QA Step 9b hit the API boundary directly and found `MosaicStatus` (the `GET /api/v1/mosaics/{id}` response model) still returns the full `footprint` range-list on every status poll — same complaint as the CLI, just on the other boundary: a status check doesn't need spatial payload, only a plotting/spatial consumer would.
*   **Trigger:** Live QA Step 9b (API/CLI parity check for `mosaic-status`).
*   **Fix:** Removed `footprint` (and its `_coerce_footprint` validator binding) from `MosaicStatus` in `src/api/schemas.py`. `_coerce_moc_footprint` itself is unchanged and still used by `TileCreate`/`TileRead`, which legitimately need footprint. `GET /api/v1/mosaics/{id}` needed no route change — FastAPI's `response_model` already drops any ORM attribute not declared on the schema. `MosaicStatus` now returns `id, filename, target_plate_scale, ra, decl, status, project_id, tile_id, epoch_id, band_id, instrument_id` — bare FK ids stay (legitimate for API consumers, unlike the CLI table) but no MOC-derived payload, matching the CLI status view on both boundaries.
*   **Regression test added:** `test_get_mosaic_status_returns_mosaic` updated to assert `"footprint" not in body` (`src/api/tests/test_mosaics.py`).

###### 2026-07-28 — `genTests` bug: Redis-down at dispatch time permanently orphans the job row
*   **Bug:** `mosaic_service.create_mosaic` and `ingest_service.create_ingest_batch` both commit their `Level3Mosaic`/`IngestBatch` row as `PENDING` *before* calling `.delay()` to dispatch the Celery task, with no `try/except` around that call. When the broker is unreachable at that exact moment, `.delay()` raises and propagates uncaught — the row is already committed, so it's left `PENDING` forever with no task ever entered into the queue. Unlike the worker-crash case (Step 10), there's no eventual redelivery here (nothing was ever queued to redeliver), so this is strictly worse: a permanently orphaned row, a direct violation of the Stuck Database States guardrail.
*   **Trigger:** Live QA Step 12 (`docker compose stop redis` immediately before `create-mosaic`) — confirmed via the actual traceback (`kombu.exceptions.OperationalError` raised from `mosaic_service.py:113`, after `db.commit()` at line 110) and a direct DB check showing the row committed `PENDING` with no further activity.
*   **Fix:** both functions now wrap their `.delay()` call in `try/except Exception`; on failure they mark the just-created row `FAILED`, commit that, and re-raise the original exception so the caller still sees a clear error — mirrors the crash-handling pattern `run_mosaic_drizzle`/`run_ingest_batch` already use internally, just applied to the dispatch-time gap instead of the mid-task gap.
*   **Regression tests added:** `test_create_mosaic_marks_failed_and_reraises_when_dispatch_fails` (`src/services/tests/test_mosaic_service.py`), `test_create_ingest_batch_marks_failed_and_reraises_when_dispatch_fails` (`src/services/tests/test_ingest_service.py`).
*   **Related, deferred to doc 29:** the worker-crash case (Step 10) surfaced a separate, harder gap — a task that's already `IN_PROCESS` when its worker is killed has no reliable/prompt recovery path either (Celery's Redis transport defaults to a 3600s visibility timeout before redelivery, effectively inert for QA-timescale observation). That needs a periodic reconciliation/watchdog mechanism, not a dispatch-time try/except — tracked in memory as part of doc 29's scope, not fixed here.

###### 2026-07-28 — `genTests` bug: `populate-demo-project` picked an arbitrary tile, not one with real data
*   **Bug:** `cmd_populate_demo_project` tessellated the target region into a tile grid, then did `tile = tiles[0]` — the first tile in generation order, with no relationship to which tiles actually overlap real ingested data. Live QA Step 13 against a real 100-file batch produced 22 tiles, only 4 of which had any associated `Level2Calibration` rows (confirmed via `tile_level2_calibration_association` counts); `tiles[0]` was one of the 18 empty ones, so `cluster_epochs` correctly found nothing and the run aborted with "No epochs generated (no calibrations in range)." A regular tessellation grid over an arbitrary region routinely produces empty edge tiles — this isn't specific to this dataset.
*   **Trigger:** Live QA Step 13 (`populate-demo-project` full coordinator run against real fiducial data).
*   **Fix:** added `tile_service.tile_with_most_calibrations(db, tile_ids) -> int | None`, which queries `tile_level2_calibration_association` and returns whichever tile actually has the most real overlap (or `None` if every tile has zero). `cmd_populate_demo_project` now uses that instead of positional indexing, and aborts with a clearer message ("No tile in the tessellated region overlaps any ingested calibration") when `None`, rather than silently proceeding on an empty tile and failing two steps later with a message that doesn't point at the real cause. General principle applied per explicit user direction: never dereference a collection by position without a reason to pick that particular element — always select by an explicit criterion (`np.any()`-style), even in one-off coordinator/dev-tooling code.
*   **Regression tests added:** `test_tile_with_most_calibrations_returns_the_best_tile_id`, `test_tile_with_most_calibrations_returns_none_when_no_tile_has_any` (`src/services/tests/test_tile_service.py`); `test_cmd_populate_demo_project_aborts_when_no_tile_overlaps_data` (`src/api/tests/test_cli.py`).
*   **Scope note:** the broader question of whether `populate-demo-project` should ship with a small curated fiducial dataset (so it doesn't require a user to hand-supply real files + hand-derive `--ra`/`--decl`/`--band-id`/`--instrument-id` via SQL) is GitHub issue #34, already open — explicitly left as-is per user decision, since this command is a manually-invoked smoke path, never run in CI, and doesn't warrant building fixture infrastructure for a single test.