# Skill: Log GitHub Issue
**Trigger Command:** `logIssue <description>` — also invoked implicitly whenever you ask to log
something as tech debt / a feature request / a bug that has no active code change to attach it to.

**Action:**
1. Determine the category: `tech-debt`, `enhancement`, or `bug`. If ambiguous, ask which applies.
2. Draft a title (imperative, ≤70 chars) and a body with three sections: What, Resolution
   condition / Acceptance criteria, and Source (how/when it was surfaced).
3. Present the drafted title, body, and label to the user for confirmation. Do not file silently.
4. On confirmation, run `gh issue create --title "..." --body "..." --label <label>`.
5. Report back the created issue number and URL.

**Constraints:**
- No git branch, commit, or PR — issue-tracker-only, never touches the working tree.
- `gh issue create` is explicitly pre-authorized for this skill only. This does not extend to
  `gh pr create` or any other `gh` write command — PRs remain text-only per CLAUDE.md's PR Workflow rule.
- Labels are fixed to `tech-debt`, `enhancement`, and `bug`. A new category needs the user's
  go-ahead before inventing a label.
