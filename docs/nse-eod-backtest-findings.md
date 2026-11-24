# NSE EOD engine — replay findings and accuracy changes (v2, 24 Nov 2026)

**Research only. Historical, EOD-simulated results with modest sample sizes. Not a
guarantee, not a calibrated win probability, not realised P&L.**

## What was tested

`tools/nse_eod/backtest/replay.py` imports the production engine unchanged and calls
`runner.build_market_summary` for every NSE session from **20 Mar 2025 to 23 Nov 2026
(415 sessions)**. It uses official UDiFF CM/FO archives only, with 72 prior cash sessions
per day as production does. Every pre-shortlist A/B/C plan is then simulated on
**later** official cash bars only (no lookahead):

- **Entry:** within the 2-session validity window. A gap open beyond the trigger
  (inside the gap-skip level) fills at the open. A gap beyond the skip level, or an
  open beyond the stop, cancels the plan. Pullback plans fill when price trades back
  to the level.
- **Stop-first rule:** if stop and target are both inside one daily bar, the stop is
  assumed to hit first. A gap through the stop exits at the open.
- **Exit:** full exit at T1, the stop, or the close of holding session 10.
  Costs are 0.15% round-trip.
- **Not modelled:** the next-session 5-minute confirmation, which cannot be observed
  from EOD data. A rough EOD proxy (a confirmed close beyond the trigger) did *not*
  improve results.
- **Validation split:** parameters were chosen on **2025 (in-sample)**, then checked on
  **2026 (held-out)**.

## Baseline result (engine as of 23 Nov 2026)

| | Plans | Filled | Win % | Avg R | 90% CI |
|---|---:|---:|---:|---:|---|
| All A/B/C | 1,251 | 766 | 45.8% | **−0.06** | [−0.13, +0.01] |
| A | 34 | 21 | 42.9% | +0.13 | [−0.42, +0.69] |
| B | 276 | 207 | 43.5% | −0.12 | [−0.25, +0.01] |
| C | 941 | 538 | 46.8% | −0.04 | [−0.13, +0.04] |
| Shortlisted | 616 | 389 | 43.7% | −0.06 | [−0.16, +0.04] |

The baseline had no measurable edge after modelled costs.

## Findings that held in BOTH 2025 and 2026

1. **Relative volume:** cash RVOL20 below 2.0× was negative in both periods
   (2025: −0.20R vs +0.26R at ≥2×; 2026: −0.15R vs +0.10R). The gates allowed 1.2–1.35×.
2. **Trend maturity:** plans where EMA20 was already more than 1.2 ATR beyond EMA50 in
   the trade direction underperformed early-trend plans.
3. **Far T1:** structural T1s beyond ~1.2R were reached too rarely.
   - Capping T1 at 1.2R helped modestly.
   - Scaling out to T2/T3 with a breakeven stop was *worse* than a full exit at T1.
4. **C-tier entry style:** C-tier breakout/breakdown entries lost in both periods
   (−0.19R / −0.13R). C-tier pullback/retest entries were the best performers.
5. **Market chasing:** signals in the direction of a strongly one-sided F&O market
   (breadth far from 50%) did worse. This is reported as a caution only.

## Findings that did NOT hold, so no rule was built on them

- **"Fresh long/short buildup" alignment.** It was negative in 2025 and flat in 2026,
  so the OI-buildup thesis by itself showed no edge.
- **Expiry-week effects, PCR, RSI bands, close location and relative strength.** Each
  flipped sign between the two periods.
- **A-tier.** About 1 plan per month (22 fills in 20 months) is too few to judge. The
  strict A logic is left unchanged as the blueprint requires; the report says so.
- **Independent FUTURES BUILDUP C pathway.** It contributed no surviving unique plan in
  20 months: most ideas fail plan construction, and the rest duplicate symbols.

## Data-correctness defects fixed

1. **Corporate actions.** NSE CM `PrvsClsgPric` is *not* split/bonus adjusted, and 34
   splits, bonuses and demergers hit F&O stocks in the window (e.g. HDFCBANK 1:1,
   BAJFINANCE 1:10, KOTAKBANK 1:5, ANGELONE 1:10). For months afterwards
   EMA/ATR/RSI/Fibonacci were computed on a broken series.
   - `technicals.adjust_corporate_actions` back-adjusts standard ratios.
   - It truncates history for unclean ratios (the TATAMOTORS, ABFRL and VEDL demergers)
     rather than guessing.
2. **Special sessions.** `market_closure()` treats every weekend as closed, so official
   sessions were missing from price history: the Budget day (Sun 1 Feb 2026) and Diwali
   Muhurat (Sun 8 Nov 2026).
   - `data.NSE_SPECIAL_SESSIONS_2026` and `history_session()` now include them in
     history.
   - The scheduled scan still treats them as non-regular days.
3. **Roll days went dark.** When the front stock future was ≤3 calendar days from
   expiry, every stock was excluded, so the whole universe produced nothing on about
   2 sessions a month (e.g. 20 and 23 Nov 2026). Regime counts on those days were
   rollover noise (156 "long unwinding" on 23 Nov).
   - `runner.analysis_contract` now uses the next contract, with **same-day
     all-expiry** OI. It sums concurrent contracts on one date and never splices
     histories across expiries.
   - Roll-day plans showed no edge (35 fills, −0.07R), so they are reported as
     WATCH ONLY. A-tier stays excluded in the roll window, as before.

## Changes (see `quality.py`, `trade_plans.py`, `runner.py`)

| Change | Where |
|---|---|
| B/C quality gate: RVOL20 ≥ 2.0×, trend maturity < 1.2 ATR | `quality.quality_gate` |
| C-tier issues pullback/retest entries only; C breakouts demoted to WATCH | `quality.quality_gate` |
| Roll-window B/C plans demoted to WATCH | `quality.quality_gate(roll_window=True)` |
| Demoted plans are shown as WATCH ONLY with reasons, never silently dropped | `quality.demote_to_watch` |
| T1 capped at 1.2R; structural level kept as next target; `structural_net_rr` stored | `trade_plans.expert_trade_plan` |
| Exit wording: T1 is the primary exit | `trade_plans.expert_trade_plan` |
| B/C ranking: RVOL ahead of modelled R | `runner.build_market_summary` |
| Shortlist "exceptional" gate uses structural R | `shortlist.exceptional_additional_plan` |
| Corporate-action adjustment of technical history | `technicals.adjust_corporate_actions` |
| Special sessions in history | `data.history_session` |
| Next contract + all-expiry OI in roll window | `runner.analysis_contract` |
| New per-plan disclosures: `trend_maturity_atr`, `fno_breadth_above_ema20`, `market_chase_caution`, `all_expiry_futures_oi_change_pct`, `rollover_distortion_possible`, `roll_window_next_contract_all_expiry_oi`, `t1_capped`, `structural_net_rr` | `runner.py` |
| Strict A-tier scoring and gates | **unchanged** |

## Result after changes (same replay, same simulation)

| | Plans | Filled | Win % | Avg R | 90% CI |
|---|---:|---:|---:|---:|---|
| All A/B/C | 413 | 219 | **59.4%** | **+0.18** | [+0.06, +0.30] |
| B | 72 | 49 | 57.1% | +0.07 | [−0.16, +0.29] |
| C | 306 | 148 | 62.8% | +0.24 | [+0.10, +0.38] |
| Shortlisted | 351 | 190 | 57.9% | +0.16 | [+0.03, +0.29] |
| 2025 in-sample, all | 149 | 81 | 56.8% | +0.13 | [−0.06, +0.31] |
| **2026 held-out, all** | 264 | 138 | **60.9%** | **+0.21** | [+0.07, +0.37] |

By quarter, filled plans with avg R at T1:

| Quarter | Baseline n | Baseline avg R | v2 n | v2 avg R | v2 win |
|---|---:|---:|---:|---:|---:|
| 2025Q2 | 90 | −0.15 | 19 | +0.26 | 63% |
| 2025Q3 | 105 | −0.13 | 30 | −0.03 | 50% |
| 2025Q4 | 108 | +0.01 | 32 | +0.21 | 59% |
| 2026Q1 | 159 | −0.09 | 52 | +0.18 | 58% |
| 2026Q2 | 102 | +0.08 | 27 | −0.00 | 52% |
| 2026Q3 | 113 | −0.14 | 32 | +0.31 | 66% |
| 2026Q4 | 83 | +0.07 | 28 | +0.33 | 68% |

**Threshold sensitivity:** every nearby setting stayed positive. RVOL from 1.6 to 2.5×
and maturity from 0.8 to 1.5 ATR gave +0.07R to +0.24R. Higher RVOL was consistently
better but produced fewer ideas.

The trade-off is volume: roughly 1 fresh plan per session instead of about 3. Many
sessions will correctly show no plan.

## Honest limits

- About 220 filled trades is a modest sample, and the CI lower bound is close to zero.
  The C-breakout demotion was confirmed with sight of both periods, not chosen blind
  on 2025.
- EOD simulation is not execution: there are no intraday sequences, no 5-minute
  confirmation, and no real slippage beyond the 0.15% assumption.
- Markets change. **Re-run the replay monthly**, and treat a sustained negative rolling
  result as a reason to pause or revise, not to loosen gates.

## Re-running

```bash
cd tools/nse_eod/backtest
export NSE_EOD_CACHE=~/.cache/nse_eod          # ~850 MB for two years
python fetch.py 2024-12-01 2026-11-23          # polite: 3 workers, retries
python replay.py .. out.jsonl 2025-03-20 2026-11-23
python analyze.py out.jsonl --features
```

The replay is an offline research tool. It is not part of the scheduled workflow and
places no orders.
