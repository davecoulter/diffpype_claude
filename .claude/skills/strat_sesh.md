# Skill: Strategy Session — Code & Architecture Review
**Trigger Command:** `stratSesh on [filename.md]`

**Demeanor:** Succinct and technical. No padding. Present findings as a structured briefing, then go interactive. The user drives the depth.

**Action:**
Read `docs/architecture/[filename.md]` and all files it touched. Produce the following briefing in order:

---

## 1. Structural Changes
What was added, modified, or removed — at the module/class/function level. One line per item. Group by layer (config, DB, API, worker, frontend, tests).

## 2. Data Flow Changes
How data moves through the system differently after this doc. Describe the before/after for any changed paths: request → service → DB → response, task dispatch → worker → queue, etc. Use concrete function names. Skip flows that didn't change.

## 3. Code Review Highlights
3–6 bullet points covering the most notable patterns, non-obvious decisions, or potential concerns in the implementation. Be specific — name the file, function, and line if relevant. This is not a rubber-stamp; flag anything worth a second look.

---

After the briefing, output a **Drill-Down Menu** listing the areas the user can explore further. Format:

> Want to dig deeper into any of these?
> - **A** — [topic]
> - **B** — [topic]
> - **C** — [topic]
> (or ask me anything)

Then wait. Respond to whatever the user picks — one topic at a time, at whatever depth they request. Stay in the session until the user is done.
