# Infrastructure Topology

Every `docker-compose` service, its internal module layers, and how monitoring tools observe it. Solid lines are data flow; dashed lines are "watches/observes." Click the ⛶ icon for a fullscreen, zoomable view.

```{mermaid}
%%{init: {"flowchart": {"nodeSpacing": 30, "rankSpacing": 35, "diagramPadding": 40}}}%%
flowchart TB
    dbeaver(["DBeaver — host DB client"]):::monitor

    subgraph network["Docker Compose Network: diffpype_net"]
        direction TB

        subgraph db_c["db (Postgres)"]
            direction LR
            db_spacer_l[" "]:::spacer
            db[("Postgres<br/>+ Q3C / HealpixAlchemy")]:::repo
            db_spacer_r[" "]:::spacer
            db_spacer_l ~~~ db
            db ~~~ db_spacer_r
        end

        subgraph redis_c["redis"]
            redis[("Redis")]:::repo
        end

        subgraph api_c["api (FastAPI)"]
            direction TB
            api_http["FastAPI App<br/>main.py"]:::apiLayer
            api_routes["Routes<br/>jobs.py · meta.py"]:::apiLayer
            api_admin["sqladmin<br/>admin.py"]:::apiLayer
            api_schemas["Schemas<br/>schemas.py"]:::apiLayer
            api_service["Service Layer<br/>job_service.py"]:::apiLayer
            api_cli["CLI<br/>cli.py"]:::cliLayer
            api_core["Core<br/>config · logger · tracing"]:::coreLayer
            api_db["DB Session / ORM<br/>session.py · models.py"]:::repo

            api_http --> api_routes
            api_http --> api_admin
            api_routes --> api_schemas
            api_routes --> api_service
            api_admin --> api_db
            api_service --> api_db
            api_cli --> api_service
            api_http --> api_core
            api_cli --> api_core
        end

        subgraph worker_c["worker (×2 instances: light, heavy_memory)"]
            direction TB
            w_spacer[" "]:::spacer
            w_app["Celery App<br/>celery_app.py"]:::workerLayer
            w_base["Base Task<br/>base_task.py"]:::workerLayer
            w_tasks["Tasks<br/>tasks.py"]:::workerLayer
            w_core["Core<br/>config · logger · tracing"]:::coreLayer
            w_db["DB Session / ORM"]:::repo

            w_spacer ~~~ w_app
            w_app --> w_base --> w_tasks --> w_db
            w_app --> w_core
        end

        subgraph ui_c["ui (React / Vite)"]
            direction TB
            ui_view["Dashboard<br/>DashboardPage.tsx"]:::uiLayer
            ui_client["API Client<br/>api.ts"]:::uiLayer
            ui_view --> ui_client
        end

        subgraph jaeger_c["jaeger"]
            jaeger_node["Jaeger"]:::monitor
        end

        subgraph flower_c["flower"]
            flower_node["Flower"]:::monitor
        end

        subgraph portainer_c["portainer"]
            direction LR
            p_spacer_l[" "]:::spacer
            portainer_node["Portainer"]:::monitor
            p_spacer_r[" "]:::spacer
            p_spacer_l ~~~ portainer_node
            portainer_node ~~~ p_spacer_r
        end
    end

    ui_client -->|HTTP| api_http
    api_service -->|dispatch task| redis
    w_app -->|consume light queue| redis
    w_app -->|consume heavy_memory queue| redis
    api_db --> db
    w_db --> db

    portainer_node -.-> api_c
    portainer_node -.-> worker_c
    portainer_node -.-> ui_c
    portainer_node -.-> db_c
    portainer_node -.-> redis_c
    flower_node -.-> redis_c
    jaeger_node -.-> api_c
    jaeger_node -.-> worker_c
    dbeaver -.-> db_c

    classDef apiLayer fill:#3B6EA5,stroke:#1F4066,color:#fff
    classDef workerLayer fill:#C97A3D,stroke:#8A4F24,color:#fff
    classDef repo fill:#4C8C6B,stroke:#2E5842,color:#fff
    classDef uiLayer fill:#8462B0,stroke:#553C78,color:#fff
    classDef cliLayer fill:#6B7280,stroke:#454A52,color:#fff
    classDef coreLayer fill:#A9B4BC,stroke:#6D7882,color:#1a1a1a
    classDef monitor fill:#F4E7EA,stroke:#C0546A,color:#7A2B3B,stroke-dasharray: 4 3
    classDef containerBg fill:#313D45,stroke:#5A6C77,color:#fff
    classDef spacer fill:transparent,stroke:transparent,color:transparent
    classDef networkBg fill:transparent,stroke:#5A6C77,color:#fff

    class db_c,redis_c,api_c,worker_c,ui_c,jaeger_c,flower_c,portainer_c containerBg
    class network networkBg

    linkStyle default stroke:#D9A64A,stroke-width:2.5px
```

## Legend

**Layers**

| | |
|---|---|
| <span style="display:inline-block;width:14px;height:14px;background:#3B6EA5;border:1px solid #1F4066;"></span> | API layer |
| <span style="display:inline-block;width:14px;height:14px;background:#C97A3D;border:1px solid #8A4F24;"></span> | Worker layer |
| <span style="display:inline-block;width:14px;height:14px;background:#4C8C6B;border:1px solid #2E5842;"></span> | Repository / data store |
| <span style="display:inline-block;width:14px;height:14px;background:#8462B0;border:1px solid #553C78;"></span> | UI layer |
| <span style="display:inline-block;width:14px;height:14px;background:#6B7280;border:1px solid #454A52;"></span> | CLI layer |
| <span style="display:inline-block;width:14px;height:14px;background:#A9B4BC;border:1px solid #6D7882;"></span> | Core / cross-cutting infra |
| <span style="display:inline-block;width:14px;height:14px;background:#F4E7EA;border:1px dashed #C0546A;"></span> | Monitoring tool |

**Connections**

| Style | Meaning |
|---|---|
| Solid line | Data flow (producer → consumer) |
| Dashed line | Watches / observes (monitor → target) |

## Container Responsibilities

| Container | Responsibility |
|---|---|
| `db` | Persists all application state — the single source of truth |
| `redis` | Celery broker + result backend, queues work between dispatchers and workers |
| `api` | Serves the HTTP API, admin panel, and CLI; validates input and dispatches work |
| `worker` (×2: `worker_light`, `worker_heavy`) | Same image/codebase, deployed as two instances with different queue subscriptions and resource limits — `light` for fast I/O-bound tasks, `heavy_memory` for memory/compute-intensive ones |
| `ui` | Frontend for dispatching jobs and viewing status |
| `jaeger` | Collects and visualizes distributed traces via OTLP |
| `flower` | Real-time Celery task/worker monitoring dashboard |
| `portainer` | Docker management UI for all running containers |

```{note}
The layer taxonomy shown here (API / Worker / Repository / UI / CLI / Core) is a first pass, agreed as a starting point. A more rigorous breakdown — separating the Service layer from Data Access, and flagging where `sqladmin` bypasses the Service layer entirely — is an open follow-up, not yet reflected in this diagram.
```
