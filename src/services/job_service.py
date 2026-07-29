"""Shared job-status service layer for API and CLI boundaries.

The Stage-0 dummy-job dispatch/lookup helpers that originally lived here were
removed when the ``DummyImage`` scaffolding was decommissioned (doc 29). The
stuck-job reconciliation/watchdog service (``reconcile_stuck_jobs``) is scoped
to doc 30 and will land here.
"""
