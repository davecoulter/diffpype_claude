# Diffpype

A lightweight DAG worker/queue skeleton for orchestrating distributed data-reduction and ML tasks: FastAPI + Celery (Canvas primitives) + PostgreSQL (Q3C / HealpixAlchemy) + Redis + React.

This repository is the **generic orchestration base** — auth/RBAC, task dispatch, retry/DLQ handling, observability, and CI/docs scaffolding — with no domain-specific data-reduction logic baked in yet. It's meant to be a starting point for other astronomical, Q-based worker/queue systems, not a finished product.

## Quick Start

```bash
cp .env.example .env
```

```bash
docker compose build
```

```bash
docker compose up -d
```

```bash
docker compose exec api diffpype-manage reset-db
```

Once running:

| Service | URL | Purpose |
|---|---|---|
| API | http://localhost:8000 | FastAPI app, routes, docs at `/docs` |
| Admin | http://localhost:8000/admin | sqladmin dashboard (login: `ADMIN_USER` / `ADMIN_PASSWORD` from `.env`) |
| UI | http://localhost:5173 | React dashboard for dispatching/monitoring jobs |
| Flower | http://localhost:5555 | Celery task/worker monitoring |
| Jaeger | http://localhost:16686 | Distributed tracing (OTLP) |
| Portainer | http://localhost:9000 | Docker container management |

## Documentation

Full architecture docs (numbered design stages, CLI guide, infrastructure diagrams) are built with Sphinx and hosted on Read the Docs. See `docs/architecture/index.md` for the design history and `docs/diagrams/infrastructure_topology.md` for a full service/data-flow diagram.

## Project Status

This is a **Stage 0 walking skeleton** — the reusable plumbing is complete and tested (98%+ coverage), but no astronomical detection/reduction logic has been added yet. If you're forking this as a base for a new project, everything here is meant to be kept; domain-specific logic goes on top.