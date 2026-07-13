##### 25: Interactive System Diagrams
**Version:** 0.1
**Authored by:** Claude, per the Claude-Authored Docs exception in `.claude/context/gemini_rules.md` — this doc codifies a design worked out directly with the user in conversation, not a Gemini-drafted spec.

###### Preamble
This document adds Mermaid-based architecture diagrams to the Sphinx documentation build, rendered client-side with lightweight pan/zoom interactivity. It is scoped narrowly to the rendering infrastructure and the first diagram (infrastructure topology, as already agreed with the user in conversation) — refining the diagram's layer taxonomy further is a separate, still-open follow-up, not part of this doc's scope.

###### 1. Sphinx Mermaid Integration
*   **Directive:** Enable Mermaid diagram rendering within the existing MyST-based Sphinx build.
*   **Behavior:**
    *   Add `sphinxcontrib-mermaid` to the `test` dependency group in `pyproject.toml`.
    *   Add `"sphinxcontrib.mermaid"` to the `extensions` list in `docs/conf.py`.
    *   Use the default client-side rendering mode — Sphinx emits the Mermaid source plus a script tag; the diagram renders in the reader's browser via mermaid.js at view-time. Do not configure the Mermaid CLI (`mmdc`) pre-rendering mode — it requires Node.js and a headless browser in the build environment, which this project's Sphinx build does not have and should not need.
*   **Testing:** After adding a diagram to `docs/diagrams/`, verify `sphinx-build -b html docs docs/_build/html -W` completes with zero warnings, and that the resulting HTML output contains the rendered `<div class="mermaid">` / mermaid.js script tags.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 2. Diagrams Folder & Toctree
*   **Directive:** Create a dedicated, Sphinx-built location for system diagrams — distinct from `prd.md`/`tech_debt.md`, which are deliberately excluded from the build.
*   **Requires:** §1's `sphinxcontrib-mermaid` extension must be enabled first — this section adds the content that extension renders.
*   **Behavior:**
    *   Create `docs/diagrams/index.md` with a toctree pointing to individual diagram pages.
    *   Create `docs/diagrams/infrastructure_topology.md` containing the infrastructure topology diagram already developed with the user in conversation (containers, internal module layers, monitoring connections), plus a legend and a container-responsibility reference rendered as plain Markdown tables alongside it — not embedded in the diagram itself.
    *   Add `diagrams/index` to the main toctree in `docs/index.rst`.
*   **Testing:** Covered by §1's Sphinx build verification — the new toctree entry must not produce an "orphaned document" warning under `-W`.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 3. Interactive Pan/Zoom
*   **Directive:** Give large diagrams comfortable scroll-to-zoom, drag-to-pan, and fullscreen navigation, without page-level browser zoom.
*   **Requires:** §2's `docs/diagrams/infrastructure_topology.md` must exist first — there is nothing to pan/zoom until a diagram is actually rendered.
*   **Behavior:**
    *   Use `sphinxcontrib-mermaid`'s own built-in support rather than a hand-rolled implementation: set `mermaid_d3_zoom = True` and `mermaid_height = "70vh"` in `docs/conf.py`. `mermaid_fullscreen` (the ⛶ expand-to-modal button) is already on by default.
    *   Do not vendor a third-party pan/zoom library or write custom init JS — the extension's native support works correctly both inline and inside its own fullscreen modal, since it's built with direct knowledge of Mermaid's async rendering lifecycle. (An earlier custom `svg-pan-zoom` implementation was built, debugged, and then removed in favor of this — see Logs.)
*   **Testing:** Manual — after building the docs, open `docs/diagrams/infrastructure_topology.html` in a browser and confirm scroll-wheel zoom, click-drag pan, and the fullscreen ⛶ button all work.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 4. Environment Variables
*   **Directive:** None required — this doc introduces no new configuration.

###### 5. Dependencies & Packages
*   **Directive:** Add the tools needed for diagram rendering and interactivity.
*   **Packages:** Add `sphinxcontrib-mermaid` to the `test` dependency group in `pyproject.toml`. No other packages or static assets are needed — pan/zoom/fullscreen come from the extension's own built-in config (§3), not a vendored library.
*   **Mocking:** None.

###### 6. CLAUDE.md Compliance
*   **Toctree Registration:** Add `25_documentation_diagrams` to the toctree in `docs/architecture/index.md`. Separately, `docs/diagrams/index` must be added to the main toctree in `docs/index.rst` (§2) — both are required for a clean `-W` build.

###### Logs

###### 2026-07-09 — Implementation (Claude Sonnet 5)
*   **§1 Sphinx Mermaid Integration:** Added `sphinxcontrib-mermaid` (unpinned; `uv lock` resolved `v2.0.3`) to the `test` group. Registered `sphinxcontrib.mermaid` in `docs/conf.py`'s `extensions`, plus `mermaid_version = "11.4.1"`. Confirmed client-side rendering: the built HTML loads `mermaid.esm.min.mjs` from a CDN and embeds the raw diagram source for browser-side rendering — no Node.js/Mermaid CLI involved.
*   **§2 Diagrams Folder & Toctree:** Created `docs/diagrams/index.md` and `docs/diagrams/infrastructure_topology.md` (the topology diagram developed with the user in conversation — all `docker-compose` services as containers, internal module layers, monitoring connections, legend). Registered `diagrams/index` in `docs/index.rst`'s toctree and `25_documentation_diagrams` in `docs/architecture/index.md`'s toctree.
*   **§3 Interactive Pan/Zoom:** Vendored `svg-pan-zoom` v3.6.1 (fetched directly from jsdelivr CDN, 29,768 bytes, verified as valid minified JS) into `docs/_static/js/`. Wrote `mermaid-panzoom-init.js` using a `MutationObserver` (not a fixed-delay timer) to reliably catch Mermaid's asynchronously-rendered SVG and attach pan/zoom once it actually appears. Registered both via `html_js_files`.
*   **Verification:** `sphinx-build -b html docs docs/_build/html -W` — zero warnings, both new pages built cleanly. Confirmed `svg-pan-zoom.min.js` and `mermaid-panzoom-init.js` present in build output. Full test suite: 115 passed, 98.25% coverage (unaffected, as expected for docs-only work).

###### 2026-07-09 — Bug found during implementation

*   **Bug: vendored static JS files referenced in HTML but never copied into the build output.** `html_js_files` correctly emitted `<script>` tags for both new files, but `docs/_static/js/` was empty in `docs/_build/html/_static/js/` — the rest of the theme's own JS (`theme.js`, `badge_only.js`) still appeared, since those ship bundled with `sphinx_rtd_theme` itself, independent of project config. Root cause: `docs/conf.py` never set `html_static_path`, so Sphinx had no project-level static folder to copy from. Fixed by adding `html_static_path = ["_static"]`. Caught by explicitly verifying build output contents (`ls`), not just the absence of build warnings — a clean `-W` build does not catch a missing static-asset-copy step.
*   **Bug: `Uncaught TypeError: Failed to execute 'observe' on 'MutationObserver': parameter 1 is not of type 'Node'`.** Found by the user manually opening the built page in Chrome and checking the console — a live-browser check a Sphinx build has no way to catch. Root cause: `html_js_files` injects `<script>` tags in `<head>`, which execute immediately as the parser reaches them, before `<body>` exists in the DOM. The init script called `MutationObserver.observe(document.body, ...)` while `document.body` was still `null`. Fixed by guarding on `document.readyState`: if `"loading"`, wait for `DOMContentLoaded` before touching `document.body`; otherwise (script ran late) proceed immediately.
*   **Bug: `Uncaught TypeError: Failed to set the 'a' property on 'SVGMatrix': The provided double value is non-finite.`** Found the same way — manual browser check, immediately after the previous fix. This one originates inside the vendored `svg-pan-zoom.min.js` itself, not the init script: it's a known failure mode when `svgPanZoom()` is called before the target SVG has valid, non-zero computed dimensions. The `MutationObserver` correctly detected *that* the SVG element existed, but not *that* the browser had finished laying it out — those are different moments. Fixed by polling `getBoundingClientRect()` via `requestAnimationFrame` (bounded to 30 attempts) until real dimensions are reported, only then calling `svgPanZoom()` — verifying the actual precondition rather than guessing a fixed delay.
*   **Bug: pan/zoom controls never appeared, with no console error.** Initially misdiagnosed as a CSS conflict between a `.mermaid svg { width/height: 100% }` rule and `svg-pan-zoom`'s internal sizing, so that rule was removed. This masked the real bug and made it worse: the `tryInit` retry loop had no logging on its failure path, so it was silently exhausting all 30 attempts and never calling `svgPanZoom()` at all — with nothing in the console to reveal that. Fixed the diagnostics first (added a `console.warn` on exhaustion, logging the measured `boxWidth`/`boxHeight`/`viewBox`), which revealed the actual cause on the next test: Mermaid's rendered SVG has `width="100%"` but *no height at all* (no attribute, no CSS), so it was rendering at a genuine 0×0 on-screen size — `viewBox` was valid, but `getBoundingClientRect()` correctly reported zero, and `svg-pan-zoom` had nothing to measure. The original `.mermaid svg { width/height: 100% }` rule was restored — it was never the problem; removing it was. Lesson: add failure-path diagnostics *before* removing a fix on a theory, not after.
*   **Bug: the CSS fix above didn't resolve it — `boxWidth`/`boxHeight` stayed 0 even with correct sizing CSS in place.** Added deeper diagnostics: dumped `getComputedStyle()` for the SVG and its full ancestor chain up to `<body>`. Every value came back as an empty string, and the chain stopped after only 2 elements with no parent — the signature of an element that isn't part of the live, rendered document at all. Root cause: Mermaid renders into a temporary, offscreen sandbox element to measure text/layout using the real browser engine, then discards it once it builds the actual final SVG. The `MutationObserver` was catching *that transient sandbox element* mid-flight, not the real one later inserted into the page — `viewBox` read fine (it's just an attribute, readable even on a detached node), but `getBoundingClientRect()`/`getComputedStyle()` correctly reported nothing, since there was no live rendering context. Added an `svg.isConnected` guard to skip disconnected matches — necessary, but not sufficient on its own (see next entry).
*   **Bug (final): even with the `isConnected` guard, the real SVG's insertion into the live page never triggered a new `childList` mutation the `MutationObserver` could catch, and nothing logged at all — not success, not the "gave up" warning.** This meant Mermaid's final reveal of the diagram doesn't happen via a fresh node insertion the way the fix assumed — most likely a style/attribute change on an already-present element, which a `childList`-only observer can't see. Rather than keep chasing Mermaid's exact internal DOM sequence, replaced the `MutationObserver` entirely with a simple `setInterval` poll (every 250ms, bounded to 15s total): re-check every currently-matching `.mermaid svg` each tick, initialize any one that's connected with real geometry. This sidesteps needing to know *which* mutation type Mermaid actually uses — confirmed working live: controls visible, diagram genuinely pan/zoomable. Removed the diagnostic-only success/failure logging once confirmed, so the shipped site doesn't log on every page load.

###### 2026-07-10 — Pivot: replaced the custom pan/zoom stack with `sphinxcontrib-mermaid`'s native support

*   **Discovery:** user feedback on the working custom implementation surfaced a real problem — a "expand to fullscreen" icon (⛶) already existed and opened a modal, but pan/zoom didn't work inside it. Investigation of the extension's source (`sphinxcontrib/mermaid/__init__.py`) found it ships **two built-in features**: `mermaid_fullscreen` (defaults to `True` — this was the already-active ⛶ modal, never explicitly enabled) and `mermaid_d3_zoom` (defaults to `False` — the actual D3-powered pan/zoom, works both inline and inside the fullscreen modal). The extension also exposes `mermaid_height`/`mermaid_width` sizing config. This is the root cause of the whole prior debugging saga: the extension's own fullscreen feature was silently active the entire time, and every custom fix was built and debugged *around* an undiscovered, competing implementation rather than the actual gap (zoom not being turned on).
*   **Action:** removed the entire custom stack — `docs/_static/js/svg-pan-zoom.min.js` (vendored library), `docs/_static/js/mermaid-panzoom-init.js` (custom init script, including all the `isConnected`/polling logic from the debugging above), `docs/_static/css/mermaid-panzoom.css`, and the corresponding `html_js_files`/`html_css_files` entries in `conf.py`. Replaced with two config lines: `mermaid_d3_zoom = True` and `mermaid_height = "70vh"`. Net effect: ~150 lines of custom JS/CSS and a vendored third-party dependency replaced by 2 lines of first-party config, maintained by people who actually understand Mermaid's rendering lifecycle.
*   **Lesson:** should have checked the extension's own capabilities before reaching for a third-party library and custom JS. Worth remembering for future doc scoping: before building custom interactivity around a Sphinx extension, check its own config surface first.
*   **Additional content fixes, same round (user feedback items 3–5):**
    *   Moved the Legend out of the Mermaid diagram entirely — it was competing for `viewBox` space and distorting the diagram's aspect ratio. Now rendered as two plain Markdown tables (Layers, Connections) in `infrastructure_topology.md`'s prose, using inline HTML `<span>` color swatches.
    *   Shortened all subgraph titles (e.g. `"api container (FastAPI)<br/>Serves the HTTP API, admin panel, and CLI..."` → `"api (FastAPI)"`) — the full responsibility sentences were causing label/content overlap and skewing Mermaid's automatic sizing for some containers (too cramped for `redis`, oversized for `db`). Moved the full sentences into a new "Container Responsibilities" Markdown table below the diagram instead.
    *   Added a `containerBg` classDef (`fill:#232B30,stroke:#4A5A63`) applied to all 9 container subgraphs, so container boundaries are visually distinct from the outer network background.
*   **Verification:** `sphinx-build -W` zero warnings; confirmed the D3 zoom script is present in build output; full test suite 115 passed, 98.25% coverage (unaffected, as expected).

###### 2026-07-10 — Further diagram refinements from live user feedback

*   **Merged `worker_light`/`worker_heavy` into a single `worker` subgraph.** Both ran identical code (same image, `celery_app.py`/`base_task.py`/`tasks.py`) — drawing them as two fully separate, duplicated subgraphs implied two different codebases rather than one deployed twice with different queue/resource configs. New subgraph titled `worker (×2 instances: light, heavy_memory)`; both `consume light queue`/`consume heavy_memory queue` edges to `redis` now originate from the same node. Mermaid has no native "stacked cards" node shape (unlike draw.io/AWS-style icon sets) to visually represent "multiple instances" — this is the honest text-based equivalent within its actual capabilities. Also reduced Portainer's/Jaeger's monitoring fan-out by 2 edges each as a side effect, modestly helping their own box-sizing.
*   **Added a `%%{init: {"flowchart": {"nodeSpacing": 30, "rankSpacing": 35}}}%%` directive** to tighten Mermaid's default layout spacing, in response to `portainer`/`db` rendering with oversized boxes relative to their single-node content. Root cause: Mermaid's auto-layout reserves horizontal room for high fan-out (Portainer watches 6 things, `db` receives from multiple sources across the diagram's width) — this is a real limit of the layout engine, not a styling bug, and the directive is a modest mitigation, not a full fix.
*   **Verification:** `sphinx-build -W` zero warnings; full test suite unaffected.

###### 2026-07-10 — Spacer-node fixes for title overlap and off-center nodes

*   **Worker subgraph's wrapped 2-line title overlapped its first content node.** Mermaid doesn't offer a "reserve space above content" option directly. Fixed with a standard Mermaid trick: an invisible spacer node (`w_spacer[" "]`, `classDef spacer fill:transparent,stroke:transparent,color:transparent`) connected via an invisible edge (`~~~`, renders no visible line but still affects layout ordering) placed before the first real node — pushes content down without losing any of the title text.
*   **Portainer/db nodes rendered off-center within their oversized boxes** (a side effect of the high-fan-out sizing issue logged above). Attempted the same trick horizontally: flanking invisible spacer nodes on both sides (`direction LR` within the subgraph, `~~~` edges left and right), nudging Mermaid's layout algorithm toward a more centered resting position. Flagged to the user as an experiment, not a guaranteed fix — Mermaid's dagre-based layout has no native "center within subgraph" primitive; positioning emerges from edge-length/crossing minimization, not a direct centering directive.
*   **Verification:** `sphinx-build -W` zero warnings; full test suite unaffected. Visual outcome pending user confirmation.

###### 2026-07-10 — Reordered subgraph declarations (positioning experiment)

*   User confirmed the spacer-node fixes worked well — Portainer/db boxes shrank *and* centered as a side effect of removing the fan-out-driven sizing pressure. Two follow-ups from the same round: `dbeaver` was rendering clipped at the diagram's right edge (its position is entirely driven by `db`'s position, since that's its only connection), and a request to reposition `db` between `api`/`worker` and above `flower` for simpler-looking routing.
*   Mermaid has no direct x/y placement for subgraphs — declaration order is the main available lever, used as a soft hint by the dagre layout algorithm alongside edge relationships. Reordered the subgraph declarations: `db_c` moved to between `api_c` and `worker_c`; `flower_c` moved to directly after `db_c`. Expectation set with the user that this is a nudge, not a guarantee — visual outcome (including whether `dbeaver` is no longer clipped) pending confirmation.
*   **Verification:** `sphinx-build -W` zero warnings; full test suite unaffected.
*   **Result: made it worse, not better.** `db_c` stayed on the far right regardless — declaration order lost to the actual edge-pull from `api_db`/`w_db` — and introduced more edge-crossing than before. Reverted to the original declaration order (`db_c, redis_c, api_c, worker_c, ui_c, jaeger_c, flower_c, portainer_c`). Fixed `dbeaver`'s clipping directly instead, with `diagramPadding: 40` added to the flowchart init config — a more targeted fix for the actual bug (content cut off at the canvas edge) rather than continuing to fight the layout algorithm's subgraph positioning. Verified: `sphinx-build -W` zero warnings, full test suite unaffected.

###### 2026-07-10 — Evaluated `architecture-beta` as an alternative, decided against it

*   User asked whether Mermaid's newer `architecture-beta` diagram type (a different rendering engine — Cytoscape.js-based, not the SVG flowchart renderer) might sidestep the layout limitations hit above. Built a container-only test (the internal module-level detail isn't representable in its group/service model) as a new page section, clearly labeled experimental.
*   **Confirmed working** — rendered cleanly with uniform icon-based nodes, no overlap/sizing/centering issues at all (validating that `architecture-beta`'s layout engine is genuinely more predictable for this shape of diagram). One minor bug found in the test: `flower` rendered disconnected, because the `flower`–`redis` monitoring edge was never written into the test source (not a tool limitation, just an incomplete test).
*   **Decision: not adopted.** User's assessment — real, no argument against it — is that the container-only view is necessarily "less descriptive" than the detailed flowchart: no module-level breakdown, no layer coloring, no responsibility text. Removed the experimental section; the flowchart diagram from the rounds above is the final version.
*   **Verification:** `sphinx-build -W` zero warnings; full test suite 115 passed, 98.25% coverage (unaffected).

Doc 25 is complete — `sphinxcontrib-mermaid` integration, the `docs/diagrams/` folder, native pan/zoom/fullscreen, and the infrastructure topology diagram are all shipped and verified.

###### 2026-07-10 — Small fix: light-gray outer network background

*   The outer "Docker Compose Network" subgraph never got a `containerBg` class applied (only the 9 inner containers did), so it was rendering with Mermaid's default subgraph fill — the light gray visible around the whole diagram in every prior screenshot. Added a `networkBg` classDef (`fill:transparent`, keeping the border) applied to the `network` subgraph. `sphinx-build -W` zero warnings; test suite unaffected.

###### 2026-07-10 — Line color and container fill readability

*   Making the network background transparent surfaced a real contrast problem: the default white edge lines only read against a dark background, and became hard to see once the surrounding area could show through as lighter in some contexts. Set a uniform line color via `linkStyle default stroke:#D9A64A,stroke-width:1.5px` (a warm amber) — a mid-tone color maintains reasonable contrast against both light and dark grounds, unlike white (fails on light) or black (fails on dark).
*   Lightened `containerBg`'s fill from `#232B30` to `#313D45` (and its stroke from `#4A5A63` to `#5A6C77` proportionally) per request — the containers were reading as quite dark/harsh.
*   **Verification:** `sphinx-build -W` zero warnings; full test suite unaffected.

###### 2026-07-13 — CI failure: `html_static_path` entry no longer exists

*   **Bug:** CI's Sphinx build step failed with `WARNING: html_static_path entry '_static' does not exist` (promoted to a hard error by `-W`). Discovered from a red ❌ CI run, not locally.
*   **Root cause:** `docs/conf.py` still set `html_static_path = ["_static"]` from the abandoned custom `svg-pan-zoom` stack. Once those vendored JS/CSS files were deleted, `docs/_static/` had no tracked contents — git doesn't track empty directories, so the directory itself was silently absent from a fresh checkout. It still existed as an empty, untracked directory on the local dev machine, which is why `sphinx-build` passed locally but failed in CI's clean clone.
*   **Fix:** Removed the dead `html_static_path = ["_static"]` line from `docs/conf.py`; deleted the local empty `docs/_static/` directory. Re-verified with a from-scratch build (`rm -rf docs/_build` first, to simulate a clean checkout) — zero warnings, `build succeeded.`
*   **Lesson:** for config referencing a directory populated only by generated/vendored files, verify against a clean checkout (or at least `rm -rf` the target build dir) before trusting a local Sphinx pass — stale local directory state can mask a warning that only surfaces in CI.
