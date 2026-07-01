# 03: Developer Tooling & CI/CD
**Version:** 0.1
**Date:** 2026-07-01

### Preamble
This document establishes the automated developer tooling for the Diffpype system. Before complex astronomical logic and database schemas are introduced, the repository must enforce strict Continuous Integration (CI) and automated documentation generation to satisfy the guardrails defined in `CLAUDE.md`.

### Goals
*   Automate unit testing and enforce strict code coverage rules on every pull request to prevent regressions.
*   Establish an auto-generating documentation system using Sphinx and Read the Docs (RTD) to capture method annotations and architecture documentation.

### Deliverables & Scope

**1. CI/CD Pipeline (GitHub Actions)**
*   Create a `.github/workflows/ci.yml` file.
*   **Triggers:** The workflow must run on any Push to the `main` branch, and on any Pull Request targeting `main`.
*   **Environment:** Use a fast, standard Python environment (no Docker Compose services needed yet, as Stage 0 tests use mocked dependencies).
*   **Testing & Coverage:** The workflow must execute the test suite using `pytest` and `pytest-cov`. It must enforce a strict 100% pass rate and fail the CI run if test coverage is reduced or if new functions lack unit tests.

**2. Documentation Engine (Sphinx & Read the Docs)**
*   Create a `docs/` directory for Sphinx documentation (ensure it does not conflict with existing markdown files).
*   **Sphinx Configuration:** Generate a `docs/conf.py` and `docs/index.rst`. Configure the `sphinx.ext.autodoc` extension to automatically pull Python docstrings and method annotations from the `src/` directory.
*   **Read the Docs:** Create a `.readthedocs.yaml` file at the repository root to configure the RTD build environment programmatically, ensuring Sphinx builds correctly in the cloud.

### Clarifications
*(Claude will use this section to pause and ask the human questions regarding implementation details before generating code.)*

#### Resolved (2026-07-01)
1. **Coverage enforcement:** No-regression threshold — CI measures current coverage and fails if it drops below that baseline (hardcoded via `--cov-fail-under=<N>`). 100% line coverage is not required, since Stage 0 unit tests intentionally mock DB/Celery, leaving infrastructure init lines unreachable.
2. **Sphinx scope:** Autodoc API only — Sphinx pulls docstrings and type annotations from `src/` only. Architecture markdown files remain standalone and are not part of the Sphinx build. No `myst-parser` needed.

Implementation defaults (no question needed): `sphinx-rtd-theme` as the Sphinx theme; `autodoc_mock_imports` in `conf.py` for all heavy external deps (`sqlalchemy`, `celery`, `fastapi`, etc.) so the RTD build does not require the full Python environment; Sphinx dependencies isolated in `docs/sphinx_requirements.txt` separate from the main `requirements.txt`.

### Prompts
1. Read this document and `CLAUDE.md`. Review the goals and deliverables for the Developer Tooling.
2. If you have any questions before beginning, ask them in the Clarifications section. Do not generate code yet.
3. Once clarifications are resolved, generate the `.github/workflows/ci.yml`, the Sphinx configuration files, and the `.readthedocs.yaml` file. Ensure they are properly integrated with the existing `src/` structure. Log your work.

### Logs
#### 2026-07-01
*   **Action:** Drafted v0.1. Defined the GitHub Actions CI workflow with `pytest-cov` enforcement and the Sphinx + Read the Docs configuration.
*   **Action:** Resolved clarifications (coverage threshold, Sphinx scope). See Clarifications section.
*   **Action:** Implemented Developer Tooling. File tree:
    *   `.github/workflows/ci.yml` — triggers on push/PR to `main`; installs `requirements.txt` on `ubuntu-latest` with Python 3.12; runs `pytest --cov=src --cov-fail-under=90`. Baseline coverage measured at 90% (Stage 0 mocked unit tests intentionally do not cover DB-init paths).
    *   `docs/conf.py` — Sphinx config with `autodoc`, `viewcode`, `napoleon`; `autodoc_mock_imports` for all heavy external deps; `sphinx-rtd-theme`.
    *   `docs/index.rst` — single-file autodoc reference covering `src.api`, `src.worker`, and `src.db` modules.
    *   `docs/sphinx_requirements.txt` — isolated Sphinx deps (`sphinx==8.1.3`, `sphinx-rtd-theme==3.0.2`) separate from the main Python requirements.
    *   `.readthedocs.yaml` — RTD v2 config: `ubuntu-22.04`, Python 3.12, `docs/sphinx_requirements.txt` install, `docs/conf.py` as Sphinx entry point.
    *   `requirements.txt` — added `pytest-cov==5.0.0`.
    *   `.gitignore` — added `docs/_build/`.
*   **Verification:** `sphinx-build -b html docs docs/_build/html -W` succeeded with zero warnings. `pytest --cov=src --cov-fail-under=90` passes (4/4 tests, 90% coverage).