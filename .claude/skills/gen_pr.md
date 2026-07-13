# Skill: Generate Pull Request Text
**Trigger Command:** `genPR on [filename.md]`

**Action:**
Run the following git commands internally to gather context:
- `git branch --show-current` — confirm the current feature branch
- `git log main...HEAD --oneline` — commits on this branch
- `git diff main...HEAD --stat` — files changed
- Read `docs/architecture/[filename.md]` — the intent and "why" behind the work

Then produce the following, in order:

---

**Suggested commit message** (for any remaining staged/uncommitted changes):
- Imperative mood, present tense: "Add X", not "Added X"
- First line ≤ 50 characters
- Optional body: one short paragraph on *why*, not *what* — the what is in the diff

**PR Title:**
- ≤ 70 characters
- Describes the user-visible change, not the doc number ("Secure SQLAdmin with session authentication", not "Implement doc 20 §1")

**PR Body** (output inside a fenced code block so the user can copy raw markdown):

```
## Summary
- [bullet: what changed and why]
- [bullet: what changed and why]
- [bullet: what changed and why]

## CLI Verification
All steps completed prior to PR creation via `genTests`.
- [x] Branch confirmed: `feature/[slug]`
- [x] Images rebuilt: `docker compose build [services]`
- [x] Containers recreated: `docker compose up -d [services]`
- [x] Migrations applied (or N/A — no model changes)
- [x] Test suite passed: `docker compose exec api uv run pytest --cov=src --cov-fail-under=90 -q`
- [x] Sphinx build passed (local)
- [x] `docs/diagrams/infrastructure_topology.md` updated and visually reviewed in rendered HTML — or N/A if this change didn't touch infrastructure topology

## Application QA
All steps completed and verified prior to PR creation via `genTests`.
Summarise each QA step that was run and its confirmed outcome — one line per step, past tense:
- [x] [What was tested] — [what was observed that confirmed it worked]
- [x] [What was tested] — [what was observed that confirmed it worked]

🤖 Generated with [Claude Code](https://claude.ai/code)
```


**Final reminders:**
- Output text only — do not run `gh pr create`. Open the PR via the GitHub UI.
- After the PR is merged, provide these post-merge cleanup commands — each command in its own fenced code block (one command per block, matching `genTests`' convention), not combined into a single block:

```bash
git checkout main
```

```bash
git pull origin main
```

```bash
git branch -d feature/[slug]
```
