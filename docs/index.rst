Diffpype
========

Diffpype is a distributed astronomical data-reduction and difference-imaging pipeline built on FastAPI, Celery, and PostgreSQL.

Core
----

.. automodule:: src.core.logger
   :members:
   :undoc-members:

CLI
---

.. automodule:: src.cli
   :members:
   :undoc-members:

Services
--------

.. automodule:: src.services.job_service
   :members:
   :undoc-members:

API (FastAPI)
-------------

.. automodule:: src.api.main
   :members:
   :undoc-members:

.. automodule:: src.api.schemas
   :members:
   :undoc-members:

.. automodule:: src.api.routes.jobs
   :members:
   :undoc-members:

.. automodule:: src.api.routes.meta
   :members:
   :undoc-members:

Worker (Celery)
---------------

.. automodule:: src.worker.celery_app
   :members:
   :undoc-members:

.. automodule:: src.worker.base_task
   :members:
   :undoc-members:

.. automodule:: src.worker.tasks
   :members:
   :undoc-members:

Database
--------

.. automodule:: src.db.enums
   :members:
   :undoc-members:

.. automodule:: src.db.models
   :members:
   :undoc-members:

.. automodule:: src.db.session
   :members:
   :undoc-members:

.. automodule:: src.db.seed
   :members:
   :undoc-members:
