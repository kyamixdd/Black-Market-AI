# Frontend Repair — Phase A Audit Baseline

**Audit date:** 2026-11-23  
**Repository:** `kyamixdd/Black-Market-AI`  
**Target branch:** `black-market-ai-beta`  
**Source commit:** `e213c5adccd09a7545b69ce90ec83cef127adac9`  
**Reference:** `kyamixdd/Black-Market-Ui-Demo` (visual reference only)

## Scope and method

Inspected the current branch tree and source for the shared React application, dashboard screens, chart components, design tokens, styles, web wrapper, backend API contract for candle intervals, package scripts, existing frontend service tests, root development documentation, and the reference repository's design tokens and principal dashboard/chart components.

The repository tree contains no `AGENTS.md` or `.agents/` instructions. The project-level `GLOBAL DEVELOPMENT RULES.txt` was reviewed. The current implementation and tests remain the source of truth for behavior. Reference-demo simulated portfolio, alerts, staking, and transaction behavior must not be copied into the main application.

This is a source audit. Browser interaction, visual screenshots, and local test commands were not executed in this audit stage.

## Architecture baseline

- `blackmarket-desktop/src/App.tsx` is the canonical React application.
- Tauri/Vite loads the canonical app from `blackmarket-desktop/src/main.tsx`.
- `blackmarket-web/app/page.tsx` performs web-session authentication and renders `SharedApplication`.
- `blackmarket-web/app/ui/shared-application.tsx` dynamically imports the same `blackmarket-desktop/src/App.tsx`.
- `blackmarket-web/app/layout.tsx` imports the shared desktop `index.css`, `design-tokens.css`, and `App.css`, then adds web login/startup styles.
- The frontend is already shared between web and desktop; a framework migration or separate dashboard implementation is not justified.

## Design-system baseline

- `blackmarket-desktop/src/design-tokens.css` already contains the reference palette, compact typography tokens, spacing, border, and radius values.
- The reference repository uses a closely matching monochrome token palette.
- The main app uses the reference-style terminal layout and avoids the demo's simulated business logic.
- `blackmarket-desktop/src/App.css` is approximately 64 KB and contains several appended responsive/design layers with repeated selectors and repeated media-query blocks. This is a maintainability and cascade-risk finding; it does not by itself prove a visual defect at every viewport.
- The web `globals.css` contains a small separate token subset for login/startup UI. It should be mapped to the canonical tokens where practical, not expanded into a second dashboard design system.

## Screen and route inventory

The canonical navigation exposes 14 screens. The list below records the screen and its principal state/actions from the current application. Exact action-level verification remains outstanding.

| Screen | Primary data / existing integration | Interactive areas to verify |
|---|---|---|
| Overview | market snapshot and candles; portfolio summary; heatmap; breadth; volume; long/short; risk; signals; learning; activity | market pair, market type, timeframe, chart tools/indicators, search, navigation, refresh/status |
| Markets | `/markets`, selected market snapshot/candles, strategy summaries | market selection, filters/search, row/detail actions |
| AI Signals | `/signals` | signal filters, inspect/details, navigation |
| Market Analysis | `/markets/{symbol}/candles` for each supported interval | timeframe selection, analysis controls, table scrolling |
| Portfolio | `/portfolio/summary` | portfolio views and related position actions |
| Positions | `/positions`, `/trades/orders` | position/order actions, confirmation, validation |
| Trade History | `/trades?limit=1000` | sorting/filtering, details, table scrolling |
| Intelligence | market and strategy analytics, volume/long-short endpoints | symbol/market/timeframe controls, refresh and details |
| Learning | predictions, models, performance, strategy comparison | filters, model/report detail and available lifecycle actions |
| Strategy Lab | `/research/strategies`, `/research/reports` | strategy selection, backtest/run, report open/save/export controls |
| Community Library | `/community/strategies`, favorites, strategy detail/history | search/filter/sort, favorite, detail/history, publish/edit/delete actions |
| Risk Management | `/risk/status` and risk settings | risk configuration, validation, save/apply, alerts |
| Activity | `/activity?limit=100` | filters, refresh, event detail |
| Settings | `/settings` | form controls, timeframe configuration, save/apply, error recovery |

The shared screen implementation is in `blackmarket-desktop/src/screens/DashboardScreens.tsx`; screen data orchestration and global controls are in `blackmarket-desktop/src/App.tsx`. Reusable table, summary, detail, empty-state, and header primitives are in `src/components/ui/TerminalPrimitives.tsx`.

## Evidence-backed findings

### P1 — No full interaction inventory or component-level regression coverage

The app has many controls across 14 screens. Existing desktop tests cover backend client behavior, market-data parsing, and WebSocket integration. No dedicated component-level test suite was found for navigation, timeframe button selection, modal/drawer actions, form submission, or responsive menu interactions. CI documentation reports responsive browser smoke coverage, but this audit did not execute it and it does not establish every control works.

**Required follow-up:** create a control matrix with expected action, source/state mutation, feedback, keyboard/touch behavior, and web/desktop coverage. Add targeted interaction tests around the highest-risk shared controls.

### P1 — Timeframe issue requires runtime reproduction; source wiring is present

The main dashboard renders native buttons with `aria-pressed` and `onClick={() => setTimeframe(item)}`. The market refresh effect depends on `timeframe` and requests candles with that interval. The backend candle route validates the same 12 values exposed by the UI: `1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w`.

**Conclusion:** source inspection does not show a missing click handler or unsupported interval in the active dashboard. The defect may be runtime, CSS hit-testing, request/response, or chart-state behavior and must be reproduced in the actual web and Tauri builds before changing the control.

### P2 — Legacy `MarketChart.tsx` has stale prop/data behavior

`blackmarket-desktop/src/components/charts/MarketChart.tsx` creates its chart in an effect dependent only on `height`, while its candle loader closes over `symbol`, `market`, and `timeframe`. It uses a separate `/api/markets/...` fetch path, lacks the active app's request/data validation path, and does not expose a complete error state. The canonical `App.tsx` imports `LiveMarketChart`, and `DashboardScreens.tsx` does not import `MarketChart`; this component appears legacy/unreferenced in the current screen path.

**Required follow-up:** confirm repository-wide references before removing or repairing it. Do not treat it as the active chart without evidence.

### P2 — Stylesheet cascade debt

`App.css` contains multiple successive terminal/responsive layers and duplicate selectors/media queries. A base `.terminal` rule sets `min-width: 760px`, but later shared-shell rules set `min-width: 0` and the mobile rule sets a smaller width; therefore the initial fixed minimum is overridden in the current cascade. The chart toolbar intentionally enables horizontal scrolling on narrow viewports.

**Required follow-up:** consolidate duplicate rules by component/feature after screenshot testing, preserving the current effective behavior. Do not append another global CSS patch layer.

### P2 — Responsive coverage is not proven at all required widths

The stylesheet includes mobile/tablet rules (including 820px, 540px, and 360px breakpoints), width containment, and horizontal scrolling for dense chart controls/tables. These are useful foundations, but source CSS cannot prove the required 320–1920px layouts, dropdown placement, modal bounds, or absence of hidden overflow.

**Required follow-up:** browser screenshots and overflow/interaction checks at 320, 360, 375, 390, 430, 768, 1024, 1280, 1440, and 1920px; specifically inspect the header, nav, chart toolbar, workspace forms, data tables, and modal/detail surfaces.

### P2 — Shared primitives exist but adoption is uneven

The app has canonical design tokens and `TerminalPrimitives`, but the main shell and screen components also define local headings, stats, action buttons, and page-specific structures. The long CSS file includes repeated feature-specific styling. This is an adoption/consistency audit item; refactoring should be incremental and preserve screen behavior.

### P3 — Documentation baseline is stale

Root `README.md` and `DEVELOPMENT_PROGRESS.md` cite source baseline `ee602590442d9d29060d525e1aff5539dc42f01c`, while the audited branch currently resolves to `e213c5adccd09a7545b69ce90ec83cef127adac9`. Update these references when the frontend implementation stage is documented, rather than silently treating the old baseline as current.

## Validation commands available

From `blackmarket-desktop/`:

- `npm run build` — TypeScript project build and Vite production build.
- `npm run lint` — Oxlint.
- `npm test` — frontend service tests.
- `npm run tauri:dev` — supported desktop runtime with supervised Python backend.

From `blackmarket-web/`:

- `npm run lint` — TypeScript check.
- `npm run build` — Next.js production build.
- `npm run test:security` — session and rate-limit tests.

Existing tests include backend-client, market-data, and WebSocket service tests. No command was executed as part of this source-only audit. No visual or runtime test is marked passed here.

## Phase A exit status

**Audit complete; implementation not started in this branch.**

The first implementation stage should target the active shared chart interaction path and establish reproducible browser coverage for timeframe selection, market switching, loading/error states, and mobile hit-testing. The chart control itself should not be rewritten until the runtime failure is reproduced. After that stage is verified, proceed to stylesheet consolidation and screen-by-screen interaction/responsive repairs.
