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

## Test plan
- [ ] [Specific manual verification step]
- [ ] Full test suite passes: `docker compose exec api uv run pytest --cov=src --cov-fail-under=90`
- [ ] Sphinx build passes: `sphinx-build -b html docs docs/_build/html -W`
- [ ] [Any Docker rebuild or worker restart required]

🤖 Generated with [Claude Code](https://claude.ai/code)
```


**Final reminders:**
- Confirm the post-implementation verification checklist from `run_arch.md` has been completed before opening the PR.
- Output text only — do not run `gh pr create`. Open the PR via the GitHub UI.
