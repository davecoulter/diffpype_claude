DevOps CLI Guide (``diffpype-manage``)
======================================

``diffpype-manage`` is the administrative command-line interface for Diffpype.
It shares the same :doc:`Service Layer <index>` used by the FastAPI boundary, so
every command has an exact API counterpart and identical business logic.

All examples below assume you are running inside the containerized environment.
Prefix each command with ``docker compose run --rm api`` (a one-off container) or
``docker compose exec api`` (an already-running container).

Overview
--------

.. list-table::
   :header-rows: 1
   :widths: 20 60 20

   * - Command
     - Purpose
     - Arguments
   * - ``seed-db``
     - Upsert the sysadmin user and baseline reference data.
     - *(none)*
   * - ``reset-db``
     - Drop all tables, rebuild from migrations, then auto-seed.
     - *(none)*

.. note::

   This guide covers the foundational database-management commands. The domain
   and operational commands added in later stages (``create-project``,
   ``ingest``, ``tessellate-tiles``, ``create-mosaic``, ``sync-staging``,
   ``reconcile-stuck-jobs``, ``populate-demo-project``, and their ``*-status``
   pollers) share the same Service Layer and follow the same API/CLI-parity
   contract; run ``diffpype-manage --help`` for the full list.

   ``tessellate-tiles``/``create-tiles`` take a ``--region-source``
   (``cone`` | ``project_footprint`` | ``bounding_box``) with the fields that
   mode needs (e.g. ``--ra/--decl/--radius-deg`` for ``cone``,
   ``--min-ra/--max-ra/--min-decl/--max-decl`` for ``bounding_box``), plus
   ``--overlap-only/--no-overlap-only`` to trim the grid to the region or
   materialize it fully.

``seed-db``
-----------

Upserts the ``sysadmin`` user and the baseline Instrument/Band reference rows
required for a functional sandbox. Safe (and idempotent) to run against a
freshly migrated database.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage seed-db
   Seeding database: inserting foundational sysadmin + reference records...
   Done.

``reset-db``
------------

Destructively drops every table, rebuilds the schema from Alembic migrations,
and then auto-seeds the foundational records so the sandbox is immediately
usable. Intended for local development only.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage reset-db
   Resetting database: downgrading to base (dropping all tables)...
   Rebuilding schema: upgrading to head...
   Schema reset complete. Auto-seeding foundational records...
   Seeding database: inserting foundational sysadmin + reference records...
   Done.

``sync-staging``
----------------

Dispatches a staging→canonical storage sync to the worker (which runs
``mc mirror`` in a streamed, restart-safe Celery task). ``--staging-prefix``
accepts a local path or an ``s3://`` URI; ``--canonical-prefix`` defaults to the
bucket root.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage sync-staging --staging-prefix ./data/staging --canonical-prefix raw
   Dispatched staging sync. job_id=<celery-task-id>

``reconcile-stuck-jobs``
------------------------

Fails any job left in ``IN_PROCESS`` past the staleness threshold (an
uncatchable worker crash or OOM kill can't run a task's own failure handler).
``--threshold-seconds`` overrides ``JOB_STALENESS_TIMEOUT_SECONDS`` for this
sweep; it also runs automatically on a Celery Beat schedule.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage reconcile-stuck-jobs --threshold-seconds 3600
   Reconciled 1 stuck job(s).
     IngestBatch id=9 (age=7200s) -> FAILED
