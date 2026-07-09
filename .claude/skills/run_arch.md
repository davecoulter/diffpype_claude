# Skill: Execute Architecture Document
**Trigger Command:** `runPrompt on [filename.md]`

**Action:**
When the user invokes this command, you must internally expand it into the following strict execution prompt and follow it exactly:

"Please review `docs/architecture/[filename.md]`.

Following your Model Evaluation Phase rule, analyze the complexity of this request and output your model recommendation and rationale. Then **STOP COMPLETELY** — do not read any files, write any code, or take any other action. Wait for explicit human authorization (e.g. "proceed", "engage") before continuing. This pause is mandatory even when the model choice is obvious.

Once authorized:
* **Branch first:** Confirm the feature branch already exists (run `git branch --show-current`). The branch should have been created before the arch doc was written, because the arch doc file itself is a tracked change. If we are still on `main`, stop and ask the user to run `git checkout -b feature/[short-slug]` before writing any code.
* **Dependencies:** If the document requires adding new packages, run `uv lock` afterward.
* **Database:** If the document modifies SQLAlchemy models, generate the Alembic migration using `--autogenerate` and explicitly remind me to run `alembic upgrade head` before finalizing tests.
* **Testing:** Maintain 100% test coverage for any new code.
* **Documentation:** Ensure the Sphinx build (`sphinx-build -b html docs docs/_build/html -W`) passes with zero warnings.
* **Logging:** Log your work in the MD file when finished.

**Post-Implementation Verification Checklist** — remind me to run these in order before opening a PR:
1. `git branch --show-current` — confirm we are on a feature branch, not main
2. `docker compose build api worker_light worker_heavy` — skip if only test files or docs changed
3. `docker compose up -d api worker_light worker_heavy` — recreates containers from fresh images; also clears stale worker memory
4. `docker compose exec api alembic upgrade head` — skip if no SQLAlchemy model changes
5. `docker compose exec api uv run pytest --cov=src --cov-fail-under=90 -q` — full test suite including integration tests against the real DB
6. **Sphinx — run locally, not in Docker** (docs/ is not mounted in the container): `DATABASE_URL="postgresql+psycopg2://dummy:dummy@localhost/dummy" REDIS_URL="redis://localhost:6379/0" uv run sphinx-build -b html docs docs/_build/html -W`"