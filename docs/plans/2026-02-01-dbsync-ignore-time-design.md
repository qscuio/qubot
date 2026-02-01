# Ignore Time Checks for Manual DB Sync/Check

## Context
Manual `/dbsync` (and related callback) runs `StockHistoryService.sync_with_integrity_check()`. That method currently skips on weekends and uses time-of-day (before 09:30) to adjust target dates inside `update_all_stocks_batch` and `_check_recent_data_integrity`. On Sunday 2026-02-01, manual `/dbsync` logged "Weekend, skipping sync". The user wants manual `/dbsync` and `/dbcheck` to **not** be gated by current time.

## Decision
Introduce a boolean flag (e.g. `ignore_time_checks`) for manual sync paths that bypasses weekend/time-of-day checks. Default remains unchanged for scheduled tasks.

## Scope
In-scope:
- Add optional parameter to `sync_with_integrity_check`, `update_all_stocks`, `update_all_stocks_batch`, and `_check_recent_data_integrity` to bypass weekend/time-of-day gating.
- Pass the flag from manual `/dbsync` command and callback.

Out-of-scope:
- Changing data-provider logic or trading-date APIs.
- Changing scheduled task behavior.

## Design Notes
- `sync_with_integrity_check(ignore_time_checks=True)` skips the weekend early-return.
- `update_all_stocks(ignore_time_checks=True)` skips weekend guard.
- `update_all_stocks_batch(ignore_time_checks=True)` uses `today` directly (no 09:30 pre-market adjustment).
- `_check_recent_data_integrity(ignore_time_checks=True)` uses `target_base = today` (no time-of-day adjustment).
- `/dbcheck` remains a read-only status call; it already does not block by time-of-day, so no change unless needed later.

## Risks
- Running sync on weekends may perform unnecessary work and fetch no new data. This is acceptable per user request for manual runs.

## Verification
- Manual run of `/dbsync` on weekend should execute and not log "Weekend, skipping sync".
