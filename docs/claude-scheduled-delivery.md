# Claude scheduled delivery — FnΘ Tattva NSE EOD research

This replaces the earlier ChatGPT scheduled task. GitHub Actions remains the numerical
engine of record (`.github/workflows/nse-eod-research.yml`). Two Claude scheduled tasks
retrieve, verify, enrich and deliver its output:

| Task | When (Asia/Kolkata) | Purpose |
|---|---|---|
| EOD report | 21:15 Mon–Fri | Verified current-session A/B/C plans + every old-plan review |
| Morning check | 09:45 Mon–Fri | Live check of last night's plans: gap-skip, triggered/holding, failed |

**Research only.** FnO Tattva, SEBI RA INH000016047. Never place orders, never claim
fills or P&L, never invent levels.

## Common setup (every run)

1. `today` = current date in Asia/Kolkata. Weekends, and dates listed in
   `NSE_HOLIDAYS_2026` in `tools/nse_eod/data.py`, are non-trading days.
   - Evening: deliver `MARKET HOLIDAY — NO EOD SCAN REQUIRED` and stop.
   - Morning: deliver "No session today" and stop.
2. Call `add_repo(owner="fnotattva", repo="fno", access="push")`, then clone it.
   - If GitHub access fails, say so and use the fallback route in E4.
3. Use the `gh` CLI with `-R fnotattva/fno`.

## Evening EOD report (21:15)

**E1. Find the current-session report.**
- List runs:
  `gh run list -R fnotattva/fno --workflow nse-eod-research.yml --branch main --limit 30 --json databaseId,status,conclusion,event,createdAt`.
- Consider runs created today (IST) from any event: schedule, push or dispatch.
- For each completed successful run, newest first:
  - Download it: `gh run download ID -n nse-eod-research-report -D r_ID`.
  - Accept it only if `report.json` has `requested_date == market_date == today`.

**E2. Verify the artifact.**
- Get the artifact id and `digest` from
  `gh api repos/fnotattva/fno/actions/runs/ID/artifacts`.
- Download the ZIP: `gh api repos/fnotattva/fno/actions/artifacts/ART_ID/zip > a.zip`.
- Check that `sha256sum a.zip` matches the digest. Record the run URL, event and SHA-256.

**E3. If no valid run exists:**
- If a run is queued or in progress, wait for it, polling every 60 seconds for up to
  20 minutes.
- Otherwise dispatch one: `gh workflow run nse-eod-research.yml -R fnotattva/fno --ref main`,
  with no `market_date` input. Then poll the same way.
- Never dispatch while a run is already queued or in progress.

**E4. Fallback (GitHub unreachable, or still no valid report after waiting).**
- In the clone, restore the newest state artifact if you can:
  `gh run download <latest successful run> -n nse-eod-research-state`.
- Run `python tools/nse_eod/runner.py`.
- Label the report `COMPUTED IN CLAUDE SESSION (fallback) — not the GitHub Actions record`
  and state whether tracking state was restored. Do not upload or commit anything.
- If NSE archives are not yet published, say `NO NEW VERIFIED PLANS` and explain.

**E5. Validate** as in the FnΘ Tattva blueprint:
- `status`: VERIFIED, PARTIAL or INCOMPLETE.
- `errors`, `coverage`, and the official CM/FO archive URLs for `today`.
- `tracking_state_restored`.

`INCOMPLETE`, a stale date, or a missing report means **NO NEW VERIFIED PLANS**.

**E6. Enrich with the NSE connectors, if available.** Never change engine levels.
- Run `nse-bhavcopy get_corporate_actions(symbol, today-120d, today+30d)` for every
  fresh plan and every active review.
  - Confirm any split/bonus that the engine adjusted for.
  - Flag any ex-date (split, bonus or dividend) falling inside the next 10 trading
    sessions. It may move price and invalidate levels.
- Run `nse-bhavcopy get_market_breadth(today)` and give the A/D ratio as context next
  to `coverage.fno_breadth_above_ema20`.
- If a connector is unavailable, say so in one line and continue.

**E7. Deliver one standalone report.** Follow the template in
`docs/nse-eod-delivery.md` and `README.md`, plus the v2 fields:
- `quality_gate_reasons` for demoted ideas, `trend_maturity_atr` and `market_chase_caution`.
- `t1_capped` and `structural_net_rr`.
- `rollover_distortion_possible` and `roll_window_next_contract_all_expiry_oi`.

Required content:
- Every fresh A/B/C plan, with entry, stop, T1/T2/T3 and target sources, net R,
  gap-skip, validity and reasons for and against.
- WATCH ideas, with no levels presented as calls.
- Every `active_plan_reviews` record, with priority exits first.
- Market regime breadth.
- Sources and data gaps.
- The statement that T1 is the primary exit.
- A note that replay statistics (`docs/nse-eod-backtest-findings.md`) are historical,
  not forecasts.
- If nothing qualifies, say so plainly. Never force picks.

## Morning check (09:45)

**M1.** Get the latest report whose `market_date` is the previous NSE trading session,
using the E1/E2 method.
- If none is available, say so and stop.

**M2.** Collect the symbols to check:
- Every fresh plan in `candidates`, `expert_trade_plans` and `expert_c_trade_plans`.
- Every `active_plan_reviews` record with `terminal_for_scenario` false whose status is
  not yet triggered.

For each, call `cm-market cm_get_stock_quote(symbol)`.
- `latestTimestamp` must be today. Otherwise mark the data STALE and stop
  classifying that symbol.

**M3. Classify** using the plan's own levels. For LONG plans (mirror everything for SHORT):

| Condition | Classification |
|---|---|
| `openPrice > gap_skip_level` (breakout plans) | GAP BEYOND SKIP LEVEL — DO NOT CHASE TODAY |
| `openPrice <= stop_loss`, or `lowPrice <= stop_loss` before any trigger | INVALIDATED — CANCEL |
| Breakout, `highPrice >= entry_trigger` and LTP >= trigger | TRIGGERED, HOLDING ABOVE TRIGGER — confirm 5-min close + volume on your terminal before acting |
| Breakout, `highPrice >= entry_trigger` and LTP < trigger | TRIGGERED THEN FAILED — DO NOT ENTER |
| Pullback (`entry_pattern` contains "pullback"), `lowPrice <= entry` and LTP >= entry | RETEST RECLAIMED — confirm on terminal |
| Pullback, LTP < entry and `lowPrice > stop` | AT RETEST, NOT RECLAIMED — WAIT |
| Otherwise | NOT TRIGGERED — show the distance to the trigger in % |

These cancel rules (gap-skip, open beyond stop) are the same ones used in the replay
simulation. Following them keeps live use consistent with the tested behaviour.

**M4.** Context:
- `cm_get_index_quote("NIFTY 50")` and `cm_get_index_quote("INDIA VIX")`.
- Today's volume so far for each symbol. Do not compute RVOL from partial-day volume.

**M5.** Deliver a short table, one row per symbol: classification, levels, LTP and time.
State clearly that this is a single snapshot at about 09:45, not 5-minute candle
confirmation, and that no orders were placed.
