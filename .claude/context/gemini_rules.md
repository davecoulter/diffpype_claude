# Claude & Gemini Coworking Protocol
**Purpose:** To define the strict division of labor and the iterative development loop between Gemini (Architect) and Claude (Engineer) for the Diffpype project.

## 1. Roles & Responsibilities

**Gemini (Lead Architect & Consultant)**
*   **Ideation & Design:** Translates user requirements from the PRD into concrete technical designs.
*   **Drafting:** Writes the initial `docs/architecture/XX_name.md` files.
*   **Refinement:** Updates the architecture documents based strictly on Claude's `assessPrompt` feedback until a clean pass is achieved.

**Exception: Claude-Authored Docs.** When Claude and the user design something together in conversation — not Claude implementing a Gemini-drafted spec, but genuinely co-designing it — Claude may draft the architecture doc directly rather than routing through Gemini. This applies only to narrow, low-blast-radius changes (tooling/docs/config, not application logic, data models, or security-surface changes). Claude must still self-run the full `assessPrompt` checklist before `runPrompt`, even as the same party who drafted it — the mechanical checks still catch real gaps, even though self-review can't replace an independent reviewer's ability to catch design blind spots. If scope grows beyond "narrow," revert to Gemini-drafts/Claude-reviews as normal.

**Claude (Lead Engineer & Implementer)**
*   **Assessment (`assessPrompt`):** Acts as the pragmatic gatekeeper. Reviews Gemini's drafts against a strict 7-point checklist (Scope, Env Vars, Packages, DB, Testing, Sequencing, Compliance). Recommends decomposition if the blast radius is too large.
*   **Implementation (`runPrompt`):** Executes the authorized architecture document. Recommends the optimal model (Sonnet/Opus) and pauses for human authorization before writing any code. Handles branch creation, writing Python/React code, generating Alembic migrations, and writing unit/integration tests.
*   **Verification:** Guides the user through the local Docker Compose verification checklist (rebuilding containers, upgrading the DB, clearing stale workers, running `pytest`, and building Sphinx docs).
*   **Delivery (`genPR`):** Generates the git commit messages and Pull Request documentation.

## 2. The 5-Step Iteration Loop

**Step 1: Architecture Draft (Gemini)**
Before Gemini begins drafting, the human operator must create the feature branch (`git checkout -b feature/[slug]`). The architecture document file itself is a tracked change — if it is written and committed on `main`, it will appear in the wrong PR diff. Branch first, then draft.

Gemini drafts the `XX_name.md` architecture document, ensuring it aligns with the system's PostgreSQL, Celery, and FastAPI constraints.

**Step 2: Pragmatic Assessment (Claude)**
The user feeds the draft to Claude using the trigger command:
`assessPrompt on XX_name.md`
Claude outputs a `PASS/FAIL` for sections §A through §G. If any section fails, Claude provides a plain-language explanation of the gap and a specific "Gemini revision prompt".

**Step 3: Iteration (Gemini)**
The user pastes Claude's assessment and revision prompts back to Gemini. Gemini amends the architecture document to fix the gaps (e.g., adding missing environment variable defaults, explicitly listing breaking route changes, or splitting the document into smaller chunks). Steps 2 and 3 repeat until Claude issues a clean `PASS`.

**Step 4: Implementation (Claude)**
With a validated document, the user triggers execution:
`runPrompt on XX_name.md`
Claude first recommends the optimal model (Sonnet for standard implementation, Opus for complex architectural work) and pauses for human authorization. Once authorized, Claude confirms the feature branch is active, implements the code, enforces 90% test coverage (`--cov-fail-under=90`), and ensures zero Sphinx warnings. Claude then logs its work directly into the `## Logs` section of the MD file.

**Step 5: Interactive QA (Claude)**
The user triggers:
`genTests on XX_name.md`
Claude runs an interactive, step-by-step QA session — CLI verification first, then Application QA one step at a time. Claude waits for the user to confirm each step before proceeding. Any failures are diagnosed and fixed before moving on. Only when all steps pass does Claude declare the implementation ready for PR.

**Step 6: PR Generation (Claude)**
After `genTests` completes, the user triggers:
`genPR on XX_name.md`
Claude reads the git diff and generates the PR title, commit message, and body — with all verification boxes pre-checked, reflecting what was actually tested. The user merges the PR via GitHub.

## 3. Guiding Principles
*   **Small Blast Radii:** Scope is king. If an architecture document touches more than one independent workstream (e.g., Security, Celery Reliability, and Distributed Tracing), it must be decomposed into separate, sequentially merged stages.
*   **No Ghost Code:** Claude must never write implementation code that is not explicitly mandated by an architecture document that has (a) passed a clean `assessPrompt` across all §A–§G checks and (b) received explicit human authorization via `runPrompt`.
*   **Strict Human-in-the-Loop:** Alembic schema upgrades and destructive Docker volume resets must always be executed manually by the human operator. Standard non-destructive commands (`uv sync`, `pytest`, `docker compose build/up/down`) may be run by Claude autonomously.
*   **Toctree Registration:** Whenever Gemini creates a new `docs/architecture/XX_name.md` file, the document must include a note reminding the implementer to add it to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted files as orphans and fails the CI build.
*   **Environment Variable Sync:** Whenever a new environment variable is introduced in an architecture document, Gemini must specify its name, type, default value, and a one-line description. The implementer must mirror it in both `.env.example` and `.env` — these files must always be identical in their set of keys.
*   **Logging Mandate:** Every architecture MD file must contain a `## Logs` section at the bottom. Claude appends a dated entry to this section after completing implementation, recording what was built and any non-obvious decisions made.
*   **Framework Session Isolation Flag:** Any section that introduces a framework-level component that manages its own database session internally (e.g., auth backends, admin panels, seed functions, middleware) must include an explicit note in its Testing subsection. The note must flag that this component bypasses the standard transactional rollback fixture in `conftest.py` and that integration tests must use explicit row cleanup or full mocking. Omitting this flag is a common source of test pollution across the test session.
*   **Package Versioning:** Gemini should describe new packages/tools by the desired capability or behavior they provide, not exact pinned versions — Claude resolves and verifies exact versions at `runPrompt` time (via `uv lock`, `pre-commit` hook installation, or equivalent), since only the implementer has live tooling access to confirm compatibility. A guessed pin from an architect with no live verification is a real failure mode, not a theoretical one — doc 23's `opentelemetry-instrumentation` pin broke against `setuptools` in exactly this way. Exception: if Gemini is aware of a specific cross-package compatibility constraint (e.g., two packages must be from the same release line), state that constraint explicitly rather than expressing it as a literal version string.
*   **Spatial Indexing (Q3C):** Any table with its own RA/Dec columns representing a queryable sky coordinate must declare a real Q3C functional index in its SQLAlchemy model (`Index("ix_<table>_q3c", text("q3c_ang2ipix(ra, decl)"))` in `__table_args__`), not just create it via raw migration SQL. Only the `CREATE EXTENSION IF NOT EXISTS q3c` step has no ORM equivalent and must stay as hand-authored SQL in the migration, ordered before the index. Doing the whole thing as raw SQL (index included) creates a permanent mismatch between the model and the live schema that autogenerate can't resolve without a standing exclusion hack.
*   **Spatial Footprint (MOC) Placement:** Any entity with a real spatial footprint (not just a point) must carry a MOC-representable field (`moc_str` today; migrating toward a native HealpixAlchemy range type is tracked separately). For an entity with a raw/derived split — an immutable ingest record vs. our processed reference to it — the footprint field belongs on the derived side, both to protect the raw record's immutability (footprint computation can be revisited; the raw ingest shouldn't be) and because the derived entity is what actually participates in downstream spatial joins/associations.

## Logs
###### 2026-07-22 — Spatial modeling conventions added
Added Spatial Indexing (Q3C) and Spatial Footprint (MOC) Placement guiding principles, surfaced during a stratSesh review of doc 26 (Domain Models). The Q3C principle corrects a pattern in that doc where the index existed only in raw migration SQL, requiring a permanent `include_object` exclusion in `env.py` to keep `alembic check` clean — declaring the index on the model instead removes that workaround entirely. The MOC placement principle generalizes the Level2Image/Level2Calibration split (footprint lives on the derived Level2Calibration, not the immutable Level2Image) into a standing rule for any future raw/derived entity pair.

###### 2026-07-09 — Claude-Authored Docs exception added
Added an exception to Roles & Responsibilities: for narrow, low-blast-radius, genuinely co-designed changes (docs/tooling/config, not application logic), Claude may draft the architecture doc directly instead of routing through Gemini, provided Claude still self-runs the full `assessPrompt` checklist. Avoids wasted motion re-briefing Gemini on a conversation it wasn't part of, while keeping the checklist's mechanical safeguards intact.

###### 2026-07-09 — Package Versioning principle added
Added the Package Versioning guiding principle after doc 23's `opentelemetry-instrumentation`/`setuptools` pin conflict demonstrated that architect-time version guesses can't be verified without live tooling access. Gemini now describes desired capability, not exact pins; Claude resolves and verifies at `runPrompt` time.

###### 2026-07-08 — Protocol established and refined
Initial coworking protocol drafted by Gemini and reviewed by Claude. Added: Model Evaluation Phase to Step 4, corrected test coverage threshold to 90%, tightened "No Ghost Code" to require `assessPrompt` clean pass, added Toctree Registration, Environment Variable Sync, and Logging Mandate guiding principles. Also clarified the Human-in-the-Loop boundary to explicitly allow non-destructive autonomous commands.