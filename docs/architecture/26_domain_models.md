##### 26: Domain Models & Spatial Indexing
**Version:** 0.4

###### Preamble
This document introduces the core astronomical domain schema for Diffpype. It establishes table-driven reference data, spatial indexing using Q3C and HEALPix, and sets up the strict many-to-many associations required to group calibrated Level 2 images into Tiles and Epochs for future mosaicing. *(Note: The removal of the Stage 0 `DummyImage` model is deferred to a dedicated future document, as its removal is a broader breaking change touching the API, CLI, UI, and test suite).*

###### 1. Reference Data (Table-Driven Metadata)
*   **Directive:** Support arbitrary instruments and filters without requiring code deployments.
*   **Behavior:**
    *   In `src/db/models.py`, create an `Instrument` model. `__tablename__="instruments"`. Columns: `id` (Integer, nullable=False), `name` (String, nullable=False, unique=True).
    *   Create a `Band` model. `__tablename__="bands"`. Columns: `id` (Integer, nullable=False), `name` (String, nullable=False, unique=True), `central_lambda` (Float, nullable=False).
    *   Both must inherit from `TimestampMixin`.
    *   Update `src/db/seed.py` so that `seed_step_definitions()` also seeds the standard JWST instruments (e.g., NIRCam, MIRI) and a few baseline bands (e.g., F150W, F277W) so the sandbox is ready to use immediately. It must use the same get-or-create pattern already used there for User/StepDefinition (check-then-insert) when seeding Instrument/Band, so a second seed run doesn't violate the new uniqueness constraint.
*   **Testing:** Add integration tests in `src/db/tests/test_integration.py` verifying the reference tables can be written to and read from. Verify that calling `seed_step_definitions()` twice does not raise an `IntegrityError` and does not create duplicate `Instrument` or `Band` rows. Explicitly clean up any `Instrument`/`Band` rows inserted via `seed_step_definitions()` in the test, since that function commits through its own session outside the transactional rollback fixture.
*   **Breaking Changes:** None.
*   **Compliance:** These models must be included in the single, unified Alembic migration generated at the end of this document.

###### 2. Organizational Framework & Spatial Footprints
*   **Directive:** Group observations spatially (Tiles) and temporally (Epochs) with native Postgres cone-search capabilities.
*   **Behavior:**
    *   Create a `Tile` model. `__tablename__="tiles"`. Columns: `id` (Integer, nullable=False), `name` (String, nullable=False), `ra` (Float, nullable=False), `decl` (Float, nullable=False), `delta_ra` (Float, nullable=False), `delta_decl` (Float, nullable=False), `moc_str` (Text, nullable=True), `healpix_index` (Integer, nullable=True), `coord_sys` (Integer, nullable=False, default=2000), `project_id` (Integer, FK, nullable=False).
    *   Create an `Epoch` model. `__tablename__="epochs"`. Columns: `id` (Integer, nullable=False), `start_date` (DateTime, nullable=False), `end_date` (DateTime, nullable=False), `start_mjd` (Float, nullable=True), `end_mjd` (Float, nullable=True), `project_id` (Integer, FK, nullable=False), `tile_id` (Integer, FK, nullable=False), `band_id` (Integer, FK, nullable=False).
    *   Both must inherit from `TimestampMixin`.
    *   **Q3C Indexing:** Instruct the Alembic migration (not the SQLAlchemy model directly) to enable the Q3C extension and create a spatial index. The migration's `upgrade()` function must execute `CREATE EXTENSION IF NOT EXISTS q3c;` before executing `CREATE INDEX ix_tile_q3c ON tiles (q3c_ang2ipix(ra, decl));`. The `downgrade()` function should drop only the index, not the extension.
*   **Testing:** Verify the models round-trip to the database and that the foreign keys to `Project` successfully back-populate.
*   **Breaking Changes:** None.
*   **Compliance:** Hand-edit the auto-generated Alembic migration to include the raw SQL commands for the Q3C extension and index.

###### 3. Data Products & Many-to-Many Associations
*   **Directive:** Model the inputs (Level 2 raw and calibrated) and outputs (Level 3), enforcing strict uniqueness and supporting overlapping associations.
*   **Behavior:**
    *   Create a `Level2Image` model (raw, immutable). `__tablename__="level2_images"`. Columns: `id` (Integer, nullable=False), `base_filename` (String, nullable=False), `ra` (Float, nullable=False), `decl` (Float, nullable=False), `exp_time` (Float, nullable=False), `mjd_avg` (Float, nullable=True), `target_name` (String, nullable=False), `obs_start` (DateTime, nullable=False), `instrument_id` (Integer, FK, nullable=False), `band_id` (Integer, FK, nullable=False).
    *   Create a `Level2Calibration` model (derived). `__tablename__="level2_calibrations"`. Columns: `id` (Integer, nullable=False), `level2_image_id` (Integer, FK, nullable=False, unique=True), `moc_str` (Text, nullable=True), `current_file_ext` (String, nullable=False), `plate_scale` (Float, nullable=False), `status` (Enum(JobStatus), nullable=False, default=JobStatus.PENDING).
    *   Create a `Level3Mosaic` model. `__tablename__="level3_mosaics"`. Columns: `id` (Integer, nullable=False), `filename` (String, nullable=False), `target_plate_scale` (Float, nullable=False), `moc_str` (Text, nullable=True), `instrument_id` (Integer, FK, nullable=False), `band_id` (Integer, FK, nullable=False), `epoch_id` (Integer, FK, nullable=False), `tile_id` (Integer, FK, nullable=False), `project_id` (Integer, FK, nullable=False), `job_configuration_id` (Integer, FK, nullable=True), `status` (Enum(JobStatus), nullable=False, default=JobStatus.PENDING). Add a `UniqueConstraint` on `(instrument_id, tile_id, epoch_id, band_id, project_id)`.
    *   All three models must inherit from `TimestampMixin`.
    *   Create two standard SQLAlchemy `Table` association objects for the many-to-many relationships connecting to the derived calibrations: `tile_level2_calibration_association` (Columns: `tile_id`, `level2_calibration_id`, with a `UniqueConstraint` on both) and `epoch_level2_calibration_association` (Columns: `epoch_id`, `level2_calibration_id`, with a `UniqueConstraint` on both).
    *   Add the `relationship(secondary=...)` definitions to `Level2Calibration` so it can access its `.tiles` and `.epochs`.
*   **Testing:** 
    *   Verify that a single `Level2Calibration` can be appended to multiple `Tile` objects and multiple `Epoch` objects, and that the database correctly persists the junction rows.
    *   Add tests verifying that the database enforces the `UniqueConstraint` logic—specifically that attempting to create a duplicate association or a duplicate `Level3Mosaic` row results in a database integrity error.
*   **Breaking Changes:** None.
*   **Compliance:** Run `alembic revision --autogenerate` after defining all models in §§1-3, hand-edit the Q3C index logic into the migration as noted in §2, and explicitly run `alembic upgrade head`.

###### 4. Environment Variables
*   **Directive:** Track configuration variables.
*   **Note:** `.env.example` and `.env` must remain identical.
| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| (No new variables) | | | |

###### 5. Dependencies & Packages
*   **Directive:** No new dependencies required (HEALPix and Q3C are already installed).
*   **Packages:** None.
*   **Mocking:** None.

###### 6. CLAUDE.md Compliance & Implementation Sequencing
*   **Implementation Sequencing:** Section 1 must be implemented before Section 2 (because `Epoch` requires `Band`). Both §1 and §2 must be implemented before §3 (because `Level2Image` requires `Instrument`/`Band`, and `Level3Mosaic` requires `Tile`/`Epoch`/`Instrument`/`Band`).
*   **CI Configuration:** Before running `runPrompt` to implement this document, the `postgres` service in `.github/workflows/ci.yml` must be updated to use the project's Q3C-enabled image (e.g., `ghcr.io/davecoulter/diffpype_claude-db:main` or built directly from `docker/db.Dockerfile`) instead of the stock `postgres:16` image. The Q3C extension only exists in the custom image, and CI cannot run this doc's migration without it.
*   **Toctree Registration:** Add `26_domain_models` to the toctree in `docs/architecture/index.md`.

###### Logs

###### 2026-07-22 — genTests: Docker bind-mount gap discovered and fixed
Phase 1 CLI verification (`docker compose exec api alembic upgrade head`) failed
with "Can't locate revision identified by '0007'" — `migrations/` is `COPY`'d into
`docker/api.Dockerfile` and `docker/worker.Dockerfile` at build time, not
bind-mounted, so a new migration file created on the host was invisible inside a
running container until rebuilt. Fixed by adding `./migrations:/app/migrations`
to the `api` service's volumes in `docker-compose.yml` (dev only — prod is
unaffected, it has no bind mounts at all), and removing the unused
`alembic.ini`/`migrations/` `COPY` lines from `docker/worker.Dockerfile`
entirely, since the worker never runs alembic. All Phase 1 and Phase 2 steps
re-verified and passed after the fix.

###### 2026-07-21 — Implementation (runPrompt)
*   Implemented §§1–3: added Instrument, Band, Tile, Epoch, Level2Image,
    Level2Calibration, Level3Mosaic models and the two composite-PK
    association tables to `src/db/models.py`; migration `0007` creates the
    tables and the Q3C extension + `ix_tile_q3c` index via raw SQL.
*   CI: replaced the stock `postgres:16` service in `ci.yml` with a build of
    `docker/db.Dockerfile` so the Q3C extension is available.
*   **Fix (autogenerate drift):** the Q3C functional index is migration-only
    and isn't representable in the ORM, so `alembic check` reported a spurious
    drop-index. Added an `include_object` hook in `migrations/env.py`
    excluding `ix_tile_q3c` from autogenerate comparison.
*   **Fix (Sphinx mock):** module-level `Base.metadata` in the association-table
    definitions raised `AttributeError` under autodoc's mocked SQLAlchemy.
    Added a mock-safe `try/except` guard so `sphinx-build -W` passes while
    keeping the models documented.
*   Verified: `alembic check` clean, 128 tests pass at 98.86% coverage,
    pre-commit clean, `sphinx-build -W` succeeds.