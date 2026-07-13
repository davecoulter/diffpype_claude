# Diffpype Product Requirements Document (PRD)
**Version:** 0.3
**Date:** 2026-06-30

### Preamble
This document defines the overarching workflows, user interactions, and macro-level behavior of the Diffpype system. It focuses on the "What" and "Why." Technical implementation details (the "How") are reserved for the `docs/architecture/` documents.

### Core Value Proposition
Diffpype's value is not the astronomical algorithms themselves — source detection, photometry, and cross-matching are well-understood and scriptable by any researcher. The value is the orchestration, parallelization, and bookkeeping required to run those algorithms reliably at the scale of modern surveys (Euclid, Roman, Rubin): tracking which images belong to which field/tile/filter/epoch, gating dependent stages correctly, retrying transient failures, and making the full provenance of every derived product inspectable and re-runnable.

If Diffpype successfully sets up all fields, tiles, epochs, and difference-image pairs, and gives researchers a web app to view them, diagnose reduction issues, and re-run stages, they can bring their own simple analysis scripts on top of it. What they can't easily build themselves is the massive parallelization and bookkeeping — and that same bookkeeping is the prerequisite for automation at survey scale. This distinction should drive scope decisions: build the orchestration layer as the core product; keep the science layer (detection, classification) as something that plugs into it, whether via a researcher's own script or a downstream consumer application.

### User Journey & Workflow Phases

#### Phase 0: Project Initialization
*   **Action:** The user defines a new project with specific parameters, notably a project name.
*   **System Behavior:** Diffpype creates working directories keyed to this name and reads a project configuration file that specifies the target S3-compatible storage site for interstitial files.

#### Phase 1: Spatial Definition & Image Acquisition
*   **Action:** The user identifies a spatial patch of the sky using a coordinate and a geometry (radius, bounding box, or polygon).
*   **System Behavior:** Diffpype queries an astronomical repository (initially MAST for level 2 NIRCam images; extensible to IPAC, Euclid, etc.) to acquire images within that spatial patch.

#### Phase 2: Pre-Processing (Parallel Actions)
*   **Action:** The user defines single-image operations to be performed on the acquired images. 
*   **System Behavior:** Operations like image alignment (e.g., using JHAT) are executed in parallel via the Celery worker queue.

#### Phase 3: Tessellation & Association
*   **Action:** The user defines a square, regular grid to tessellate the spatial region. Each square is a "tile," which determines the central coordinate and tangent plane of the resulting image mosaic. 
*   **System Behavior:** Diffpype determines image membership for each tile. Images within a tile are associated and grouped by bandpass (filter) and epoch. 
*   **Epoch Definition:** Users can define epochs manually via custom date ranges or automatically via a peak-finding algorithm.

#### Phase 4: Mosaic Generation (Drizzling)
*   **Action:** The user initiates mosaic creation for a given tile + filter + epoch association.
*   **System Behavior:** 
    *   **Dependency Gating:** The stacking process cannot start if required single operations (like Phase 2 alignment) on constituent images are still pending.
    *   **Execution:** Once all components are ready, Diffpype creates the corresponding database entities via the SQLAlchemy ORM and places a job on the Celery queue to drizzle the images using the JWST level 3 pipeline.

#### Phase 5: Difference Imaging
*   **Action:** Once mosaics are created, the user associates pairs of mosaics for subtraction, specifying the template mosaic and the target mosaic.
*   **System Behavior:** The user selects a difference image algorithm (Primitive numpy subtraction, SFFT, HOTPANTS, PyZOGY). The job is dispatched to the queue.

#### Phase 6: Results Visualization & Export
*   **Action:** The user inspects the resulting difference images and downloads deliverables.
*   **System Behavior:**
    *   **Canvas Visualization:** Resulting FITS files are rendered in a performant HTML canvas/pane within the React UI (utilizing tools like fitsmap or similar).
    *   **Asset URLs:** Visualized assets have dedicated URLs to allow for direct downloading.
    *   **Export Widget:** The UI provides a download widget allowing the user to select specific files to download or execute a "download all" command.

### Job Orchestration, Monitoring & Re-Execution
*   **Queue Inspection:** The status of each job on the Celery queue is fully inspectable by the user, utilizing a monitoring tool such as Flower.
*   **Failure Handling (Blocking vs. Non-Blocking):** Users define whether individual jobs are "blocking" (hard dependencies for downstream tasks). If a non-blocking task fails, the system automatically excludes the failed asset and allows the downstream DAG execution to continue.
*   **Stage Inspection & Parameter Iteration:** Users can inspect the intermediate outputs of any stage. Users can manually adjust parameters and re-run the specific upstream step.
*   **Data Staleness & Cascade Deletes:** When an upstream task is re-executed, the system automatically flags any completed downstream artifacts as "out of sync" with the new inputs. Alternatively, users can specify a "cascade delete" override to automatically wipe downstream products when upstream assets change.

### User Interfaces
*   **Web UI (React):** A visual frontend that displays polygons and allows users to select tiles to view image memberships. Interacting with a submit button pushes object definitions via the FastAPI to save state in the Postgres database.
*   **CLI:** A programmatic command-line interface capable of driving the exact same workflow without the Web UI.

### Deferred / Future Scope (v2+)
To ensure fast, iterative development of the core infrastructure, the following downstream pipeline features are deferred from the initial implementation. Per the Core Value Proposition above, the v1 MVP's job is to reliably produce fields/tiles/epochs/difference-image pairs and make them inspectable; this stage is where the "science" starts layering on top.

**Detection & Alerting Pipeline (ordered):**
1.  Source detection on difference images via SExtractor, producing catalogs.
2.  Catalog-driven photometry.
3.  Clustering subsequent detections across filter and time, associating repeat detections with the same physical source.
4.  Astrophysical validation gate: promote a cluster to candidate status based on detection count, cross-filter consistency, PSF shape matching, and artifact screening.
5.  Light curve extraction for validated candidates.
6.  Publish validated candidates to a Kafka alert stream.

Prior art for this pipeline exists in `prototype/` (e.g. `prototype/src/jwst_diff/source_match.py`) — to be reviewed and redesigned when this phase is scoped, not ported as-is. The prototype's Django/MySQL schema (`prototype/djangotutorial/diffpype/models.py`) is also the conceptual ancestor of the current Postgres schema and Celery dispatch pattern, and its notebooks (`prototype/notebooks/`) effectively served as a static proxy UI — both worth reviewing together as design reference before this phase is architected.

**Downstream Consumer Architecture (Kafka):** Diffpype's role at the end of the detection pipeline is to be a *producer* — publishing validated candidates to a Kafka topic without needing to know who consumes them. Planned downstream consumers include RISE (an ML system compiling photometry/spectra/light curves, performing host-galaxy matching and SED fits, and autoencoding these attributes) and Teglon (a gravitational-wave pipeline networking Rubin and Roman). Each downstream consumer runs its own independent worker fleet. This keeps Diffpype's internal Celery/Redis DAG orchestration focused purely on image production; Kafka is the boundary for external broadcast to consumers that may not exist yet. CLAUDE.md's Core Tech Stack Constraints do not currently mention Kafka — this should be added deliberately when this phase is actually scoped, not assumed.

**Observability & Monitoring Infrastructure:**
*   Standing up an actual Prometheus server to scrape the `/metrics` endpoint (added in architecture doc 23) and retain it as a time series, plus a Grafana dashboard for visualization/alerting. Currently the endpoint exposes request metrics but nothing collects or graphs them over time.
*   Wiring Jaeger's SPM ("Monitor" tab) to a spanmetrics-connector-backed Prometheus instance, so per-service/per-operation request-rate/error-rate/duration graphs are available directly in the Jaeger UI. Surfaced when the Monitor tab returned a 501 ("metrics querying is currently disabled") during doc 23 QA — expected, since no SPM backend is configured; tracing itself is unaffected.

### Logs
#### 2026-07-09 (2)
*   **Action:** Added a "Core Value Proposition" section — the orchestration/bookkeeping-at-scale distinction that should drive future scope decisions (build the orchestration layer; keep detection/classification as something that plugs into it).
*   **Action:** Replaced the terse Deferred/Future Scope bullets with the actual ordered detection-and-alerting pipeline (SExtractor → photometry → clustering → astrophysical validation gate → light curves → Kafka publish), plus a Downstream Consumer Architecture section describing the Kafka producer/consumer boundary and naming RISE and Teglon as planned consumers. Noted `prototype/` as prior art to review before this phase is architected, not to port as-is.

#### 2026-07-09
*   **Action:** Added an "Observability & Monitoring Infrastructure" subsection to Deferred / Future Scope, capturing follow-on work surfaced during doc 23 (Observability) QA: a real Prometheus server + Grafana dashboard, and Jaeger SPM wiring.
*   **Action:** Moved the CLI root-span tracing item out of this section to `docs/tech_debt.md` — it's a known gap in already-shipped code, not an unbuilt product feature, so it fits that document's scope better.

#### 2026-06-30
*   **Action:** Drafted v0.1 of PRD based on the user's workflow definition.
*   **Action:** Updated to v0.2. Added Job Orchestration, Monitoring & Re-Execution section.
*   **Action:** Updated to v0.3. Added Phase 6 (Results Visualization & Export) covering FITS HTML canvas rendering and download widgets. Added Deferred / Future Scope section to explicitly isolate downstream ML/photometry tasks from the v1 MVP.