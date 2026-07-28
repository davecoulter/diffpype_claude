##### 27: Schema Corrections, S3 Storage & Native Spatial Types
**Version:** 0.1

###### Preamble
This document establishes the storage foundation and spatial type corrections for Diffpype. It enforces a native S3-backed storage pattern (mocked locally via MinIO), corrects the domain schema to properly scope calibrations to Projects, and replaces the legacy `healpix-alchemy` integration with a vendored, natively supported PostgreSQL range type for spatial footprints (MOCs).

###### 1. Database Schema Corrections
*   **Directive:** Fix the calibration/image uniqueness constraints to support multi-project processing and enable idempotent upserts.
*   **Behavior:**
    *   **Level2Image:** Add a `UNIQUE` constraint to the `base_filename` column.
    *   **Level2Calibration:** Add `project_id` (ForeignKey to `projects.id`, nullable=False). 
    *   **Level2Calibration:** Drop the `unique=True` constraint on `level2_image_id`. Replace it with a composite `UniqueConstraint("level2_image_id", "project_id")`.
    *   **ORM Updates:** In `src/db/models.py`, update `Level2Image.calibration` to `Level2Image.calibrations` (a list `Mapped[list["Level2Calibration"]]`).
    *   **Backfill Strategy:** Because `level2_images`, `level2_calibrations`, `tiles`, and `level3_mosaics` currently have zero rows in every environment (verified: `src/db/seed.py` does not populate any of them, and the only test-created `Tile`/`Level3Mosaic` rows use the transactional `db` fixture and are rolled back), the new `project_id` NOT NULL column and the `moc_str` column-type replacement in §2 both require no backfill or data-conversion logic.
    *   **Migration Strategy:** Use standard Alembic `--autogenerate` for these constraints and columns, as no custom SQL is required.
*   **Testing:** Add integration tests verifying that duplicate `base_filename` inserts fail, and that the same `Level2Image` can successfully have two different `Level2Calibration` rows as long as they belong to different `Project`s.
*   **Breaking Changes:** Any existing 1:1 ORM calls referencing `image.calibration` must be updated to handle the list of `image.calibrations`.
*   **Compliance:** Generate a new Alembic migration for these changes.

###### 2. Native Spatial Range Type (Resolves Issue #26)
*   **Directive:** Replace the Text-typed `moc_str` columns with a native PostgreSQL range-type column, resolving dependency rot from the unmaintained `healpix-alchemy` package.
*   **Behavior:**
    *   In `src/db/models.py`, replace `moc_str` on `Tile`, `Level3Mosaic`, and `Level2Calibration` with a native spatial column named `footprint` (a column literally named `_str` should not hold a non-string).
    *   Create a new module `src/db/spatial_types.py`. Implement a vendored SQLAlchemy `TypeDecorator` (`MOCType`) backed by PostgreSQL's `INT8MULTIRANGE` — a single column holding a whole MOC as a set of disjoint ranges. Model it on the *design* of `healpix-alchemy`'s `Tile`/`Point` types, converting via modern mocpy's `MOC.to_depth29_ranges` / `from_depth29_ranges`. (See the Logs for why `INT8MULTIRANGE` rather than the originally-planned `INT8RANGE`, and why `astropy-healpix` is not needed.)
    *   Include a comment in `src/db/spatial_types.py` attributing the reference source (`healpix-alchemy`).
    *   Remove `healpix-alchemy` entirely from `pyproject.toml` (confirmed unused and broken).
    *   Make `mocpy` a direct, exact-pinned dependency.
*   **Testing:** Require a round-trip fidelity test in `src/db/tests/test_integration.py`. Construct a MOC object, persist it to the database through the new column type, read it back, and assert equivalence (e.g., by comparing `sky_fraction` or canonical serialization before and after).
*   **Breaking Changes:** Removes `healpix-alchemy`.
*   **Compliance:** This partially resolves backlog issue #26 — the `moc_str` → native range-type portion. `Tile.healpix_index`'s migration to its own native range-type representation (a separate column from the footprint field, per #26) is not part of this doc and remains open on the issue for a future pass.

###### 3. Native S3 Storage Service
*   **Directive:** The application must strictly use the `boto3` S3 protocol for all FITS file I/O, seamlessly swapping between local development and cloud production via environment variables.
*   **Behavior:**
    *   Update `docker-compose.yml` to include a lightweight local `minio` service container (mock S3).
    *   Create `src/services/storage_service.py`. Implement an `S3StorageService` class using `boto3` that reads `S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `S3_BUCKET_NAME` from the core Settings.
    *   Implement basic `download_file(s3_key, local_path)` and `upload_file(local_path, s3_key)` methods.
*   **Testing:** Write unit tests for `S3StorageService` mocking the `boto3` client using `pytest-mock` or `moto` to ensure paths and buckets are constructed correctly. Additionally, add a real (unmocked) integration test module (`src/services/tests/test_storage_service_integration.py`, mirroring `src/db/tests/test_integration.py`'s naming/fixture convention) that round-trips a file through a live `minio` and asserts a clear error on a missing key — the mocked unit tests alone cannot prove the real network path (application → S3-compatible endpoint) works.
*   **CI Compliance:** Per the CI Service Parity guardrail, `.github/workflows/ci.yml` must provision `minio` (stock image, no custom build needed) alongside the existing Postgres pattern — a `docker run` step + a readiness-wait step — plus the `S3_ENDPOINT_URL`/`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`S3_BUCKET_NAME` env vars, since the new integration test is a real, unmocked dependency on the service.

###### 4. Environment Variables
*   **Directive:** Ensure all new configurations are tracked and synchronized.
*   **Note:** `.env.example` and `.env` must remain identical.
| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| S3_ENDPOINT_URL | str | "http://minio:9000" | The endpoint for the S3 bucket (local MinIO or AWS). |
| AWS_ACCESS_KEY_ID | str | "minioadmin" | S3 access key (also the MinIO container root user). |
| AWS_SECRET_ACCESS_KEY | str | "minioadmin" | S3 secret key (also the MinIO container root password). |
| S3_BUCKET_NAME | str | "diffpype-data" | The target bucket for pipeline data. |
| MINIO_API_PORT | int | 9002 | Host port mapped to the MinIO container's S3 API (9000); host 9000 is taken by portainer. |
| MINIO_CONSOLE_PORT | int | 9001 | Host port mapped to the MinIO web console. |

###### 5. Dependencies & Packages
*   **Directive:** Add cloud storage and spatial manipulation packages.
*   **Packages:** Add `boto3` and `mocpy` to `pyproject.toml`. Remove `healpix-alchemy`. (`astropy-healpix` is not needed — modern mocpy does the range conversion natively.)
*   **Mocking:** `boto3`, `mocpy`, and `numpy` must be added to `autodoc_mock_imports` in `docs/conf.py`. `src/db/spatial_types.py` uses `from __future__ import annotations` so its `MOC`-typed signatures do not evaluate against the mock at import time, and it keeps its `automodule` entry (it does not need to be mock-imported itself).

###### 6. CLAUDE.md Compliance & Implementation Sequencing
*   **Implementation Sequencing:** Implement §1 (Schema Corrections) and §2 (Native Spatial Range Type) together as they touch the database models and should be bundled into a single Alembic migration. Then implement §3 (S3 Storage).
*   **Documentation Registration:** 
    *   Add `.. automodule:: src.services.storage_service` and `.. automodule:: src.db.spatial_types` to `docs/index.rst`.
    *   Update `docs/diagrams/infrastructure_topology.md` to include the new `minio` service in the topology diagram.
    *   Add `27_schema_storage_spatial_types` to the toctree in `docs/architecture/index.md`.

###### Logs

**2026-07-27 — Implementation (runPrompt)**

*Design deviation (approved before coding):* The doc's §2 anticipated a single-range
`INT8RANGE` column modeled directly on `healpix-alchemy`. That is not implementable
as a single-column footprint store: a real MOC has many disjoint intervals, and
`healpix-alchemy` only fits them in `INT8RANGE` by storing one row per interval in a
child table. Chosen approach instead: a single **`INT8MULTIRANGE`** column (Postgres
14+, we target PG16) holding the whole MOC, via a vendored `MOCType` in
`src/db/spatial_types.py`. Also dropped the planned `astropy-healpix` dependency —
modern `mocpy` exposes `to_depth29_ranges`/`from_depth29_ranges` directly, so the
`astropy_healpix.uniq_to_level_ipix` path the doc named is unnecessary. Fidelity is
coverage-equivalence (identical `sky_fraction` + empty symmetric difference), not MOC
object `==`, because normalizing to depth 29 for indexed overlap does not preserve the
original authoring order. The `moc_str` columns were renamed to `footprint` (a column
named `_str` no longer holds a string).

*Bug 1 — autogenerated migration was not runnable.* `alembic revision --autogenerate`
emitted `src.db.spatial_types.MOCType()` without importing the module (would `NameError`)
and created the `base_filename` unique and `project_id` FK with `None` names, making the
downgrade's `drop_constraint(None, ...)` calls fail. Discovered on review of the draft.
Fixed by hand-authoring `20260727_0008_...` with an explicit import and
Postgres-convention constraint names, symmetric in `downgrade()`. `alembic check`
reports no residual drift.

*Bug 2 — `psycopg2` cannot adapt multirange objects.* Binding SQLAlchemy
`Range`/`MultiRange` values raised `ProgrammingError: can't adapt type 'Range'` — native
multirange adaptation only exists in `psycopg` v3, and this project uses `psycopg2`.
Discovered by a live insert against the dev DB. Fixed by having `MOCType` bind and read
the Postgres multirange **text literal** (`{[lo,hi),...}`) instead, which psycopg2 adapts
as a plain string and SQLAlchemy already wraps in an `::int8multirange` cast.

*Bug 3 — mocpy `__eq__` raises on `None`, breaking ORM change detection.* On flush,
SQLAlchemy compares old vs. new column values; `MOC.__eq__(None)` raises `TypeError`
rather than returning `False`, so nulling or updating a `footprint` crashed. Discovered
by a live update path. Fixed by overriding `MOCType.compare_values` to treat `None`
safely and define equality as identical depth-29 coverage (also avoids spurious UPDATEs
from order-only differences).

*Bug 4 — `compare_values` also receives the `NO_VALUE` sentinel, not just `None`.* The
first `compare_values` fix guarded only against `None`, but when a column was never
loaded SQLAlchemy passes its `LoaderCallableStatus.NO_VALUE` sentinel as the old value,
which is not `None` and has no `to_depth29_ranges` — so setting a footprint on a
freshly-inserted-then-reloaded row raised `AttributeError`. Missed by the live test
(its first assignment happened in the same flush as the insert) but caught by the formal
`test_footprint_moc_roundtrip_fidelity`. Fixed by making the guard type-based:
any operand that is not a `MOC` (covering `None`, `NO_VALUE`, and any future sentinel)
falls back to identity comparison.

*Bug 5 — Sphinx `-W` failed on `MOC | None` annotations under the autodoc mock.* With
`mocpy` mocked, the annotation `MOC | None` evaluated to `mock | None` at class/def
time and raised `TypeError: unsupported operand type(s) for |`, breaking autodoc import
of `spatial_types`, `models`, and everything importing them. Fixed with
`from __future__ import annotations` in `spatial_types.py` and by stringifying the three
`Mapped["MOC | None"]` annotations in `models.py` (matching the existing forward-ref
style). Added `boto3`/`mocpy`/`numpy` to `autodoc_mock_imports`.

*Post-implementation additions (user-requested during runPrompt).* (1) Added GiST
indexes on the `footprint` column of `tiles`, `level2_calibrations`, and `level3_mosaics`
(model `__table_args__` + migration `0008`), so the doc-28 ingest/spatial-match tooling
has indexed `&&` overlap available from the start — indexing is schema-appropriate here
even though no query uses it yet in this doc. (2) Added
`test_footprint_overlap_query_returns_only_spatial_matches`, which proves the actual
capability issue #26 targets — a native multirange `&&` overlap query returns only
spatially-overlapping rows — rather than only proving storage fidelity. Verified a
live `&&` query returns the expected rows and that GiST-on-`int8multirange` is valid on
PG16. (Migration gotcha logged: a stale `.pyc` of `0008` from before the index edit ran
during re-apply, leaving the DB stamped at `0008` without the indexes; cleared
`migrations/versions/__pycache__` and re-ran a full downgrade/upgrade cycle to confirm
the corrected migration round-trips and `alembic check` is clean.)

*Verification (all green):* `pytest --cov=src --cov-fail-under=90` → 136 passed, 98.9%
coverage (`spatial_types.py`, `storage_service.py`, `models.py` all 100%);
`alembic check` clean; `sphinx-build -W` succeeded; `pre-commit run --all-files`
(ruff, ruff-format, mypy) passed. Live MinIO smoke test of `S3StorageService`
(bucket create + upload + download round-trip) passed.

*genTests additions (user-requested during Application QA).* Wrote 6 manual QA
scripts to `collab_scratch/doc27_qa/` (git-ignored, throwaway) covering base_filename
uniqueness, project-scoped calibration, footprint fidelity + overlap query, and a
MinIO up/down failure-injection pair — all dry-run and verified passing before
handoff (one real bug caught: `storage_service.py`'s import of `src.core.config`
triggers the `settings = Settings()` singleton, which requires `DATABASE_URL`/
`REDIS_URL` even for a standalone script that never uses that global instance;
worked around in the scripts' `_common.py`, not a `src/` code change).

Decided, discussing which of these deserved to become permanent automated coverage
vs. stay manual: promoted the MinIO round-trip to a real (unmocked) integration test,
`src/services/tests/test_storage_service_integration.py` (mirrors
`src/db/tests/test_integration.py`'s convention), since nothing in the existing
mocked unit tests (`test_storage_service.py`) proves the real network path works —
exactly the class of gap that produced bugs 2–4 above. This required adding `minio`
to `.github/workflows/ci.yml` (new CI Service Parity guardrail in CLAUDE.md), since
CI previously had no MinIO at all. Left the failure-injection scripts
(`qa06a`/`qa06b`) manual/uncommitted — stopping and restarting a real Docker service
mid-test needs orchestration control a plain `pytest` process doesn't have, and the
payoff is human confidence during review, not durable regression value.

*Verification after this addition:* full suite (including the new integration test,
run host-side against MinIO via a localhost override) → 138 passed, 98.9% coverage;
`pre-commit run --all-files` passed.

*Documentation cleanup (descriptive references only; historical logs left intact):*
Updated the now-inaccurate "HealpixAlchemy" mentions in `README.md`,
`docs/architecture/01_system_architecture.md`, and the `db` node label in
`docs/diagrams/infrastructure_topology.md`; added the `minio` service to that diagram.
`docs/architecture/05_database_schema.md`'s dated log of when `healpix-alchemy` was
added was deliberately not rewritten. `.claude/context/gemini_rules.md` still names
`moc_str` and "HealpixAlchemy range type" — deferred pending explicit confirmation
(meta-config change rule).