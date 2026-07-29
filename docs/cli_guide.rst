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
   commands added in later stages (``create-project``, ``ingest``,
   ``tessellate-tiles``, ``create-mosaic``, ``populate-demo-project``, and their
   ``*-status`` pollers) share the same Service Layer and follow the same
   API/CLI-parity contract; run ``diffpype-manage --help`` for the full list.

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
