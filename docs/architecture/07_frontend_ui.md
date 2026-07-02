### 07: Frontend UI Architecture & State Management
**Version:** 0.1

##### Preamble
This document establishes the architecture for the React frontend. It aims to support a scalable, unidirectional state flow that can handle thousands of astronomical images, drill-down dashboards, and dynamic UI elements without unnecessarily bloating the dependency tree.

##### 1. Client-Side Routing
*   **Directive:** Support drill-down navigation (e.g., from a high-level "Project Dashboard" grid to a specific "Mosaic Detail" page) without triggering full page reloads.
*   **Behavior:** Implement `react-router-dom` to manage client-side routing. This ensures smooth transitions and allows users to bookmark specific views or detail pages directly.

##### 2. Data Fetching & Caching
*   **Directive:** Manage the complex state of paginated grids and WebSocket updates without building custom, heavy React hooks (`useState`/`useEffect` chains).
*   **Behavior:** Implement **TanStack Query (React Query)**. It will natively handle data fetching, caching, loading spinners, and pagination. This ensures the frontend does not hammer the FastAPI backend with redundant requests when navigating between views. Standard HTML tables or lightweight grid components will be used for the UI to keep dependencies low for now.

##### 3. Dynamic DB-Driven Enums
*   **Directive:** The frontend must not hardcode the enumerations (e.g., pipeline statuses, queues, bands, or their associated colors).
*   **Behavior:** Implement a new FastAPI metadata endpoint (e.g., `GET /meta/statuses`). On initial load, the React application will fetch the active enumerations directly from the PostgreSQL database and use that data to render the traffic-light status grids dynamically.

#### Logging
The "Logs" section will record Claude's work. Please use the following format:
##### (Short summary of the work)
##### (Short summary of the work)
...
#### Logs

##### Fix: npm install for @tanstack/react-query and react-router-dom
*   **Root cause:** Both packages were correctly listed in `src/ui/package.json` since doc 07, but the `diffpype_ui_node_modules` named Docker volume was created before the rebuild and cached the old `node_modules` (Docker named volumes take precedence over image layers on mount). The packages were never actually installed in the running container, causing Vite import errors.
*   **Fix:** Stopped the `ui` container, removed the stale `diffpype_claude_diffpype_ui_node_modules` volume, and rebuilt the `ui` image. The new image runs `npm install` fresh, populating a clean volume with `@tanstack/react-query@5.101.2` and `react-router-dom@6.30.4`. Verified via `npm list`.

##### Client-Side Routing, TanStack Query, & DB-Driven Enum Metadata
*   **Client-Side Routing:** Added `react-router-dom@^6.26.2` to `src/ui/package.json`. `src/ui/src/App.tsx` refactored from a monolithic component to a routing shell: wraps the app in `<QueryClientProvider>` + `<BrowserRouter>` and declares a single `<Route path="/" element={<DashboardPage />} />`. The existing dummy-job UI extracted to `src/ui/src/pages/DashboardPage.tsx`. Structure is ready to expand with additional drill-down routes (e.g., `/jobs/:id`) without full page reloads.
*   **TanStack Query:** Added `@tanstack/react-query@^5.59.0` to `src/ui/package.json`. `DashboardPage.tsx` uses `useQuery` for the `GET /meta/statuses` fetch (cached, no redundant requests on navigation) and for polling `GET /jobs/dummy/{id}` (1 second `refetchInterval`, automatically stops when status is `complete` or `failed` via the function-form callback). `useMutation` drives the `POST /jobs/dummy` dispatch. The old manual `useState`/`useEffect`/`setInterval` chain is completely removed.
*   **DB-Driven Enum Metadata:** Added `StatusMetadata` Pydantic schema to `src/api/schemas.py`. Created `src/api/routes/meta.py` with `GET /meta/statuses`: queries the live Postgres `job_status` enum type via `SELECT unnest(enum_range(NULL::job_status))` so that any future Alembic migration adding a new status value is automatically surfaced to the UI without a frontend change. Response includes `value`, `label` (title-cased), and `color` (traffic-light palette). Meta router registered in `src/api/main.py`. `docs/index.rst` updated to include the new routes. `src/ui/src/api.ts` updated with `getStatuses()` function and `StatusMetadata` interface. `DashboardPage` builds a `colorMap` from the fetched metadata — the hardcoded `STATUS_COLORS` constant is gone.
*   **Tests:** Added `src/api/tests/test_meta.py` (1 unit test, mocked DB session verifying DB query is called and response structure/colors are correct). Total: 5 tests, 5 passed, 92.50% coverage.
