# Skill: Execute Architecture Document
**Trigger Command:** `runPrompt on [filename.md]`

**Action:**
When the user invokes this command, you must internally expand it into the following strict execution prompt and follow it exactly:

"Please review `docs/architecture/[filename.md]`.

Following your Model Evaluation Phase rule, please analyze the complexity of this request, recommend the optimal model, and **pause for my authorization**.

Once authorized:
* **Branch first:** Confirm the feature branch already exists (run `git branch --show-current`). The branch should have been created before the arch doc was written, because the arch doc file itself is a tracked change. If we are still on `main`, stop and ask the user to run `git checkout -b feature/[short-slug]` before writing any code.
* **Dependencies:** If the document requires adding new packages, run `uv lock` afterward.
* **Database:** If the document modifies SQLAlchemy models, generate the Alembic migration using `--autogenerate` and explicitly remind me to run `alembic upgrade head` before finalizing tests.
* **Testing:** Maintain 100% test coverage for any new code.
* **Documentation:** Ensure the Sphinx build (`sphinx-build -b html docs docs/_build/html -W`) passes with zero warnings.
* **Logging:** Log your work in the MD file when finished.

**Post-Implementation Verification Checklist** — remind me to run these in order before opening a PR:
1. `git branch --show-current` — confirm we are on a feature branch, not main (branch should have been created before the arch doc was written)
2. `docker compose build api worker_light worker_heavy` — if models, packages, or worker code changed
3. `docker compose up -d api` — recreate the api container from the fresh image
4. `docker compose exec api alembic upgrade head` — apply any new migrations
5. `docker compose restart worker_light worker_heavy` — clear stale in-memory task code
6. `docker compose exec api uv run pytest --cov=src --cov-fail-under=90` — full test suite
7. `sphinx-build -b html docs docs/_build/html -W` — zero Sphinx warnings before PR"