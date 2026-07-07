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
     - Insert the foundational ``StepDefinition`` records.
     - *(none)*
   * - ``run-dummy``
     - Dispatch a dummy Celery job through the shared service layer.
     - ``--sleep SECONDS``
   * - ``get-dummy``
     - Fetch and display a ``DummyImage`` status as an ASCII table.
     - ``--id ID``
   * - ``reset-db``
     - Drop all tables, rebuild from migrations, then auto-seed.
     - *(none)*

``seed-db``
-----------

Inserts the foundational ``StepDefinition`` rows required for a functional
sandbox. Safe to run against a freshly migrated database.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage seed-db
   Seeding database: inserting foundational StepDefinition records...
   Done.

``run-dummy``
-------------

Dispatches a dummy sleep job. A fresh correlation ID is generated and threaded
through the service layer into the Celery worker, so the same ID appears in both
the API and worker JSON logs. The ``--sleep`` argument controls the simulated
work duration in seconds (default ``5``).

.. code-block:: console

   $ docker compose run --rm api diffpype-manage run-dummy --sleep 60
   Dispatched dummy job. correlation_id=3f2a..., job_id=7c1e..., image_id=42

``get-dummy``
-------------

Fetches a single ``DummyImage`` by its integer ID and prints it as a
human-readable ASCII table, followed by an elapsed-time summary — ``Run Time``
once the job has started, or ``Queue Time`` while it is still pending.

.. code-block:: console

   $ docker compose run --rm api diffpype-manage get-dummy --id 42
   +------+------------+----------------+...
   |   id | status     | latest_job_id  |...
   +======+============+================+...
   |   42 | in_process | 7c1e...        |...
   +------+------------+----------------+...
   Run Time: 12s

If no image exists with the given ID, a clear error message is printed:

.. code-block:: console

   $ docker compose run --rm api diffpype-manage get-dummy --id 999
   Error: No DummyImage found with id=999.

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
   Seeding database: inserting foundational StepDefinition records...
   Done.
