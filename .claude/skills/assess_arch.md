# Skill: Assess Architecture Document
**Trigger Command:** `assessPrompt on [filename.md]`

**Demeanor:** Be cautious and thorough. This project prioritizes robustness over delivery speed. Surface ambiguities early, ask clarifying questions rather than making assumptions, and recommend scope changes when they serve long-term stability — even if it slows the current doc down.

**Action:**
Read `docs/architecture/[filename.md]`. Do NOT write any implementation code. Run the full checklist below on every invocation — never skip items that passed in a prior pass, as doc edits can introduce new issues indirectly.

For each failing item, produce: (a) a plain-language description of what is missing, and (b) a revision prompt the user can paste into Gemini. Revision prompts must convey the *what* and *why* of the required change clearly enough that Gemini can implement it without ambiguity — but must not ghostwrite the solution. State the problem, the location, and the recommended direction; leave the prose to Gemini. Do not dictate exact sentences or replacement text. If a choice must be made, flag it as **Decision Required** for the user before formulating the prompt.

---

**§A — Scope & Decomposition**
- [ ] The document addresses a single coherent concern.
- [ ] Each section has a concrete, testable outcome.
- [ ] No section defers a decision that is required to implement another section in the same doc.

*If this section fails:* Recommend a decomposition — propose specific doc titles, a one-sentence scope per doc, and a suggested implementation order. Frame this as a recommendation, not a hard block.

**§B — Environment Variables**
- [ ] Every new env var is explicitly named (e.g. `ADMIN_PASSWORD`).
- [ ] Every new env var has a type, a default value, and a one-line description.
- [ ] The doc notes that `.env.example` and `.env` must be kept in sync.

**§C — Dependencies & Packages**
- [ ] Every new package/tool is named, with the desired capability/behavior it provides. Exact version pins are resolved and verified by the implementor at `runPrompt` time (via `uv lock`, `pre-commit` hook install, or equivalent), not dictated by the architecture doc — unless the architect is flagging a specific known cross-package compatibility constraint (e.g., "X and Y must be from the same release line"), which should be stated as a constraint, not a literal version string.
- [ ] Any package that uses framework-style class keyword arguments (e.g. `model=User`) is flagged as a candidate for `autodoc_mock_imports` in `docs/conf.py`.

**§D — Database**
- [ ] If any SQLAlchemy model is modified, an Alembic migration is explicitly required.
- [ ] The migration strategy is specified (autogenerate vs. hand-authored, and why).
- [ ] No new `nullable=False` column is added without a backfill strategy for existing rows.

**§E — Testing**
- [ ] Every new business logic function has a corresponding unit test requirement.
- [ ] Any integration test that commits outside the transactional rollback fixture is flagged for explicit cleanup.
- [ ] New API endpoints are tested for both success and error responses.

**§F — Sequencing & Dependencies**
- [ ] Dependencies between sections are explicit (e.g. "§2 requires §1's migration first").
- [ ] Breaking changes (renamed routes, dropped fields, changed signatures) are called out.
- [ ] If the doc introduces auth, it specifies what happens to existing unauthenticated paths.

**§G — CLAUDE.md Compliance**
- [ ] No patterns conflict with existing guardrails (API/CLI parity, TDD, Sphinx mandate, env var sync).
- [ ] If a new Python business logic module is introduced, a `docs/index.rst` `automodule` entry is noted.
- [ ] If a new architecture doc is being created, a `docs/architecture/index.md` toctree addition is noted.

---

**Output format:**
1. **Summary table first** — a markdown table with columns `Section | Result`, one row per §A–§G, `✅ PASS` / `❌ FAIL` / `✅ PASS (N/A)` / `⚠️ Decision needed`. No elaboration in the table itself.
2. **"What fixed cleanly" bullet list** — on re-assessment passes, briefly note which prior failing items are now resolved, before detailing anything still open.
3. **Failing items, each under its own subheading** — what's missing + a plain-language explanation. Use a comparison table instead of prose wherever a side-by-side (e.g. option A vs. option B, old behavior vs. new) would be clearer. If a failing item represents a genuine design decision (not a gap with an obvious fill), flag it as **Decision Required**, present the options with a recommendation and rationale, and wait for the user to confirm before including it in the Gemini prompt block.
4. **Decomposition recommendation** — only if §A fails.
5. **Consolidated Gemini revision prompt** — a single copyable fenced code block combining all confirmed revision instructions. Label it clearly so the user can paste it directly. Only include items where the fix is confirmed (i.e., no open Decision Required items remain unresolved).
6. **Exit condition** — when all items pass or are explicitly N/A: *"This document is ready for `runPrompt`."*