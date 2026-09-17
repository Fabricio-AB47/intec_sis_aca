# Loading Optimizations

## Scope

- Load the public/authenticated evaluation form only when opened, using the existing lazy-view pattern.
- Load each of the seven Moodle panels on demand, with a local Suspense boundary. The Moodle header, navigation and parent-owned filters remain mounted.
- Keep the dashboard refresh interval at 30 seconds. Loading-state changes no longer restart its initial fetch. Concurrent refreshes are guarded; hidden tabs refresh when they become visible again.
- Share concurrent identical evaluation GET requests only. Results and failures are removed when settled, with no response TTL or persistent cache.
- Clear pending-read references on login, logout, profile change and evaluation invalidation. An older request cannot remove a newer pending request.
- Reuse historical-evaluation identity maps, normalized search text, selected-code sets and locale formatters instead of rebuilding them for progress updates.

No SQL/schema changes, business-rule changes, altered authorization, additional POST retries or generated institutional data are part of these optimizations. The existing administrative attribution, preview authorization, per-block tokens, offsets and retry semantics are unchanged. Per-view state lifetime is unchanged; this does not introduce recovery across full browser reloads.

## Build Measurements

Vite production build on 2026-09-17. Decimal kB, JavaScript assets only:

| Asset | Before | After | Before gzip | After gzip |
| --- | ---: | ---: | ---: | ---: |
| Initial application JavaScript | 419.42 | 399.52 | 111.74 | 107.52 |
| Initial Moodle module JavaScript | 174.34 | 24.52 | 35.97 | 5.52 |

Moodle's remaining code is not deleted: its panels are separate assets fetched when needed. These are bundle-size measurements, not claims about end-to-end latency. Global styling is intentionally unchanged.

## Verification

With Vite running at `http://127.0.0.1:5174`, from the repository root:

```powershell
& '.venv\Scripts\python.exe' frontend/tests/verify_runtime_optimizations.py
```

The test uses Python Playwright and installed Microsoft Edge. Set `FRONTEND_TEST_URL` for a different Vite URL. All API traffic and write responses are mocked; no student records, grades or official evaluations are modified.

Coverage at 1600, 390 and 320 px:

- One dashboard initial read, scheduled refresh, hidden-tab pause and simultaneous focus/visibility events.
- Awaitable dashboard load sharing and ignored responses/loading cleanup from a superseded profile.
- Every Moodle panel's navigation and deferred code loading, plus retained parent-owned course filters.
- Historical generation with an interrupted block, preserved checkpoint, renewed tokens, completed-block non-repetition, aggregate counts and progress-dialog reopening.
- Identical concurrent reads, fresh subsequent reads, error recovery, distinct period queries, auth/invalidation isolation and independent POST requests.
- Anonymous access to the deferred public evaluation form.

Frontend TypeScript/build, focused ESLint and `git diff --check` must also pass.
