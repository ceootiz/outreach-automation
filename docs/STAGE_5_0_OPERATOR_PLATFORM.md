# Stage 5.0 Production Operator Platform

Stage 5.0 turns the outreach system into a faster operator platform. It does not add hidden sending, browser automation, stealth behavior, captcha bypassing, or autosend. All execution still follows the existing safe channel policies and human-confirmed workflows.

## What Was Added

- Performance package in `src/performance/`:
  - `CacheManager` for short-lived UI/search/analytics cache.
  - `SessionCache` for local UI recovery state.
  - `VirtualPage` helpers for large list/table paging.
  - preload/render budget helpers for 5k/10k/25k lead workloads.
  - `LatencyMetrics` for measuring search and operator operations.
- Command Palette:
  - `Cmd+K` / `Ctrl+K`.
  - safe navigation and operator actions.
  - global search results.
  - no message send side effects.
- Quick Review 2.0:
  - compact Outreach Session mode.
  - `J/K`, `N/P`, `Space`, `Enter`, `E`, `C`, `O`, `S`, `F`, `L`, `1/2/3`.
  - hotkeys pause while typing in text fields.
- Notification Center:
  - replies received.
  - follow-up reminders.
  - AI warnings.
  - queue failures.
- Background Task Monitor:
  - queue health.
  - job counts by status/type.
  - failed tasks.
  - retry visibility.
- Import/export hardening:
  - chunked massive import.
  - paginated contacts.
  - operator exports for leads, inbox and analytics.
- Benchmark:
  - `scripts/perf_benchmark.py`.
  - synthetic data only.
  - no real sends or live credentials.

## Performance Philosophy

Stage 5.0 focuses on reducing operator latency rather than adding risky automation.

Targets:

- fast session restore;
- responsive search;
- quick lead switching;
- no giant render passes for large datasets;
- recoverable queue state after restart.

Large datasets are handled through paging, render budgets, cache invalidation and chunked imports. The benchmark uses synthetic recipients and refuses to send real email.

## Session Recovery

The app stores local operator UI state, including active campaign and current page, through `SessionCache`. Outreach Session state already persists campaign, filters, current lead, review position, selected variant and unsaved draft through the operator session tables.

## No Unsafe Automation

Stage 5.0 keeps these guarantees:

- no autosend;
- no hidden social sending;
- no browser farming;
- no captcha bypass;
- no anti-detection logic;
- no recipient rewriting;
- no secret logging.

Command Palette actions are intentionally safe. “Start AI Draft Generation” opens/records a draft-only intent and does not queue sends. “Start Outreach Session” creates an operator review session and does not send.

## Operator Workflow

Recommended high-speed flow:

1. Import leads.
2. Generate AI drafts.
3. Open `Outreach Session`.
4. Enable `Quick Review 2.0`.
5. Use hotkeys for review/copy/open/mark-sent.
6. Watch `Уведомления` and `Задачи` for replies, follow-ups and queue health.
7. Use `Cmd+K` to jump between contacts, campaigns and screens.

## Benchmark

Run:

```bash
python scripts/perf_benchmark.py --count 1000 --reset
```

It measures:

- app/service startup;
- massive import;
- lead switching;
- AI draft render;
- inbox open;
- search;
- filters;
- session restore;
- queue monitor latency;
- paginated contacts.

The benchmark uses a temporary SQLite database by default and synthetic contacts only.

## Known Limitations

- The UI uses paginated service methods, but some existing table widgets still render classic Qt tables internally.
- Performance metrics are local process metrics, not OS-level profiling.
- Multi-window/detachable panels remain future work.
- Live connector verification remains covered by Stage 4.x controlled QA and still requires owned credentials/chats.
