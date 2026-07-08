# Claude & Gemini Coworking Protocol
**Purpose:** To define the strict division of labor and the iterative development loop between Gemini (Architect) and Claude (Engineer) for the Diffpype project.

## 1. Roles & Responsibilities

**Gemini (Lead Architect & Consultant)**
*   **Ideation & Design:** Translates user requirements from the PRD into concrete technical designs.
*   **Drafting:** Writes the initial `docs/architecture/XX_name.md` files.
*   **Refinement:** Updates the architecture documents based strictly on Claude's `assessPrompt` feedback until a clean pass is achieved.

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

**Step 5: PR Generation (Claude)**
After the user completes the post-implementation verification checklist (Docker rebuilds, Alembic upgrades, pytest), the user triggers:
`genPR on XX_name.md`
Claude reads the git diff and generates the PR title, commit message, and body. The user merges the PR via GitHub.

## 3. Guiding Principles
*   **Small Blast Radii:** Scope is king. If an architecture document touches more than one independent workstream (e.g., Security, Celery Reliability, and Distributed Tracing), it must be decomposed into separate, sequentially merged stages.
*   **No Ghost Code:** Claude must never write implementation code that is not explicitly mandated by an architecture document that has (a) passed a clean `assessPrompt` across all §A–§G checks and (b) received explicit human authorization via `runPrompt`.
*   **Strict Human-in-the-Loop:** Alembic schema upgrades and destructive Docker volume resets must always be executed manually by the human operator. Standard non-destructive commands (`uv sync`, `pytest`, `docker compose build/up/down`) may be run by Claude autonomously.
*   **Toctree Registration:** Whenever Gemini creates a new `docs/architecture/XX_name.md` file, the document must include a note reminding the implementer to add it to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted files as orphans and fails the CI build.
*   **Environment Variable Sync:** Whenever a new environment variable is introduced in an architecture document, Gemini must specify its name, type, default value, and a one-line description. The implementer must mirror it in both `.env.example` and `.env` — these files must always be identical in their set of keys.
*   **Logging Mandate:** Every architecture MD file must contain a `## Logs` section at the bottom. Claude appends a dated entry to this section after completing implementation, recording what was built and any non-obvious decisions made.
*   **Framework Session Isolation Flag:** Any section that introduces a framework-level component that manages its own database session internally (e.g., auth backends, admin panels, seed functions, middleware) must include an explicit note in its Testing subsection. The note must flag that this component bypasses the standard transactional rollback fixture in `conftest.py` and that integration tests must use explicit row cleanup or full mocking. Omitting this flag is a common source of test pollution across the test session.

## Logs
###### 2026-07-08 — Protocol established and refined
Initial coworking protocol drafted by Gemini and reviewed by Claude. Added: Model Evaluation Phase to Step 4, corrected test coverage threshold to 90%, tightened "No Ghost Code" to require `assessPrompt` clean pass, added Toctree Registration, Environment Variable Sync, and Logging Mandate guiding principles. Also clarified the Human-in-the-Loop boundary to explicitly allow non-destructive autonomous commands.