#!/usr/bin/env python3
"""One-shot NSE EOD futures/options positional research. NEVER places broker orders."""
from __future__ import annotations
import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data import Unavailable, cash_history, most_recent, url_for, market_closure
from logic import chain_metrics, expiry, num, research_candidate, tech_metrics, classify_futures, pct
from expert import expert_watch_candidate
from trade_plans import expert_trade_plan, track_expert_plans
from management import review_research_plans
from shortlist import choose_daily_shortlist

IST = ZoneInfo("Asia/Kolkata")
OUTPUT = Path("out")
EOD_SOURCE = "NSE public F&O/CM UDiFF Bhavcopy Final"

def equity_rows(rows, universe=None):
    result = {}
    for row in rows:
        sym = row.get("TckrSymb", "")
        series = row.get("SctySrs", "")
        if not sym or (universe is not None and sym not in universe):
            continue
        if series and series != "EQ":
            continue
        price, vol = num(row.get("ClsPric")), num(row.get("TtlTradgVol"))
        if price <= 0 or vol <= 0: continue
        if sym not in result or vol > num(result[sym].get("TtlTradgVol")):
            result[sym] = row
    return result

def build_market_summary(asof, fo, cm, hist):
    futures = defaultdict(list)
    option_chains = defaultdict(list)
    for row in fo:
        sym = row.get("TckrSymb", "")
        exp = expiry(row)
        if exp < asof or not sym: continue
        if row.get("FinInstrmTp") == "STF":
            futures[sym].append(row)
        elif row.get("FinInstrmTp") == "STO":
            option_chains[(sym, exp)].append(row)
    stocks = equity_rows(cm, set(futures))
    history_by_symbol = defaultdict(list)
    for old_date, old_rows in hist.items():
        for sym, row in equity_rows(old_rows, set(futures)).items():
            history_by_symbol[sym].append((old_date, row))
    picks = []
    snapshots = {}
    regimes = Counter()
    covered = Counter()
    regime_observations = []
    for sym, rows in futures.items():
        front = min(rows, key=expiry)
        ex = expiry(front)
        oi, d_oi = num(front.get("OpnIntrst")), num(front.get("ChngInOpnIntrst"))
        fp, prev_fp = num(front.get("SttlmPric")) or num(front.get("ClsPric")), num(front.get("PrvsClsgPric"))
        regime = classify_futures(pct(fp, prev_fp), pct(oi, oi - d_oi)) if oi > d_oi and prev_fp > 0 else "NEUTRAL"
        regimes[regime] += 1
        if sym not in stocks: covered["missing_cash"] += 1; continue
        options = option_chains.get((sym, ex))
        if not options: covered["missing_same_expiry_options"] += 1; continue
        cm_chain = chain_metrics(options, num(stocks[sym].get("ClsPric")))
        if not cm_chain: covered["incomplete_chain"] += 1; continue
        covered["valid_chain"] += 1
        series = sorted(history_by_symbol.get(sym, []), key=lambda pair: pair[0])
        series.append((asof, stocks[sym]))
        tech = tech_metrics([entry for _, entry in series])
        if not tech: covered["insufficient_cash_history"] += 1; continue
        covered["valid_history_and_chain"] += 1
        snapshots[sym]={"future":front,"chain":cm_chain,"tech":tech}
        if ex <= asof + timedelta(days=3):
            covered["near_expiry_excluded"] += 1; continue
        item = research_candidate(sym, front, cm_chain, tech, asof)
        if item:
            item["options_expiry"] = ex.isoformat()
            item["cash_data_sessions"] = tech["sessions"]
            picks.append(item)
            covered["qualified"] += 1
        elif regime != "NEUTRAL" and num(front.get("TtlTradgVol")) >= 100:
            regime_observations.append({
                "symbol": sym, "regime": regime, "futures_change_pct": round(pct(fp, prev_fp),2),
                "futures_oi_change_pct": round(pct(oi, oi-d_oi),2),
                "cash_close": round(tech["close"],2), "put_wall": cm_chain["put_wall"],
                "call_wall": cm_chain["call_wall"], "max_pain": cm_chain["max_pain"],
                "reason": "Did not pass all entry, wall, trend, liquidity, score and risk gates.",
            })
    picks.sort(key=lambda c: (c["score"], abs(c["futures_oi_change_pct"]),
                              c["cash_rvol20"]), reverse=True)
    regime_observations.sort(key=lambda c: abs(c["futures_oi_change_pct"]), reverse=True)
    # Separate qualitative-pattern discovery, not a softened A-tier score.
    # Draw from the whole verified NSE F&O universe, even when an options
    # chain is incomplete, but retain minimal data/liquidity guardrails.
    primary_symbols = {item["symbol"] for item in picks}
    alternatives = []
    plans = []
    c_plans = []
    for symbol, contracts in futures.items():
        if symbol in primary_symbols or symbol not in stocks:
            continue
        front = min(contracts, key=expiry)
        if expiry(front) <= asof + timedelta(days=3):
            continue
        history = sorted(history_by_symbol.get(symbol, []), key=lambda t:t[0])
        history.append((asof, stocks[symbol]))
        technical = tech_metrics([bar for _, bar in history])
        if technical is None:
            continue
        options = option_chains.get((symbol, expiry(front))) or []
        options_context = chain_metrics(options, technical["close"]) if options else None
        idea = expert_watch_candidate(symbol, front, options_context, technical, asof)
        if idea is not None:
            proposed = expert_trade_plan(idea, technical, options_context, front)
            if proposed is not None:
                plans.append(proposed)
            else:
                conditional_c = expert_trade_plan(idea, technical, options_context, front, tier="C")
                if conditional_c is not None:
                    c_plans.append(conditional_c)
                else:
                    alternatives.append(idea)
    plans.sort(key=lambda item: (
        item["pattern_priority"], item["modelled_net_rr_t1"],
        item["cash_rvol20"], abs(item["futures_oi_change_pct"])
    ), reverse=True)
    c_plans.sort(key=lambda item: (
        item["pattern_priority"], item["modelled_net_rr_t1"],
        item["cash_rvol20"],abs(item["futures_oi_change_pct"])
    ), reverse=True)
    alternatives.sort(key=lambda item: (
        item["pattern_priority"], item["relative_volume"],
        abs(item["futures_oi_change_pct"]), item["cash_turnover_inr"]
    ), reverse=True)
    covered["expert_trade_plan_candidates"] = len(plans)
    covered["expert_c_trade_plan_candidates"] = len(c_plans)
    covered["expert_watch_candidates"] = len(alternatives)
    return (picks[:12], plans[:12], c_plans[:12], alternatives[:3],
            regime_observations[:5], dict(covered), dict(regimes), len(futures),snapshots)

def track_prior(prior, current_date, cash):
    updates, kept = [], []
    for previous in prior or []:
        try:
            last = date.fromisoformat(previous["asof_date"])
            sig = previous["signal"]
            symbol, direction = sig["symbol"], sig["direction"]
            sl, entry, t1, t2 = [float(sig[k]) for k in ("stop_loss","entry_trigger","target_1","target_2")]
            delta_days = (current_date-last).days
            if delta_days > 8 or delta_days < 0: continue
            if delta_days == 0:
                # Repeated EOD scheduled checks must not reinterpret today's
                # entry and stop as a prior-session paper position.
                kept.append(previous)
                continue
            row = cash.get(symbol)
            if not row:
                kept.append(previous)
                updates.append({"id":sig["signal_id"],"status":"UNVERIFIED","reason":"Missing current cash quote"})
                continue
            high, low, close = [num(row.get(k)) for k in ("HghPric","LwPric","ClsPric")]
            sign = 1 if direction == "LONG" else -1
            touched_entry = high >= entry if sign == 1 else low <= entry
            touched_t1 = high >= t1 if sign == 1 else low <= t1
            touched_t2 = high >= t2 if sign == 1 else low <= t2
            touched_sl = low <= sl if sign == 1 else high >= sl
            close_invalid = close <= sl if sign == 1 else close >= sl
            if touched_sl and touched_entry:
                status="STOP LEVEL TOUCHED; ORDER OF INTRADAY EVENTS UNKNOWN"
            elif close_invalid: status="EXIT / INVALIDATION BY EOD CLOSE"
            elif touched_t2: status="T2 PRICE TOUCHED (ENTRY/SEQUENCE UNCONFIRMED)"
            elif touched_t1: status="T1 PRICE TOUCHED (ENTRY/SEQUENCE UNCONFIRMED)"
            elif touched_entry: status="ENTRY LEVEL TOUCHED (5-MIN CLOSE NOT VERIFIED)"
            else: status="UNTRIGGERED WATCH"
            updates.append({"id":sig["signal_id"],"status":status,"asof":current_date.isoformat(),
                            "cash_close":round(close,2)})
            if not close_invalid and (current_date-last).days < 8: kept.append(previous)
        except (ValueError, KeyError, TypeError):
            continue
    return updates, kept

def apply_coverage_status(result):
    """Keep incomplete technical coverage distinct from a verified zero-pick day."""
    coverage = result.get("coverage", {})
    missing = coverage.get("insufficient_cash_history", 0)
    valid = coverage.get("valid_history_and_chain", 0)
    if missing:
        result["status"] = ("PARTIAL EOD RESEARCH" if valid
                            else "INCOMPLETE EOD RESEARCH")
        result["errors"].append(
            f"Technical history insufficient for {missing} stocks; "
            f"{valid} stocks have valid history and chains. "
            "Empty A/B/C lists do not establish a market-wide no-trade result."
        )

def render(data):
    lines = [f"# FnO Tattva — NSE EOD OI Research | {data['market_date'] or data['requested_date']}",
             "", f"**Status:** {data['status']}", f"**Generated:** {data['generated_ist']}",
             f"**Source:** {EOD_SOURCE}", ""]
    if data.get("market_date"):
        day = date.fromisoformat(data["market_date"])
        lines += [f"- FO archive: {url_for('FO', day)}", f"- CM archive: {url_for('CM', day)}", ""]
    if data["status"] == "MARKET HOLIDAY":
        lines += [
            f"**MARKET HOLIDAY — NO EOD SCAN REQUIRED.** {data.get('holiday_reason', 'Official NSE closure')}.",
            "There was no regular NSE cash/F&O trading session on the requested date. "
            "No current-session candidates, expert opportunities, or trading levels exist.",
            "Official NSE 2026 trading holiday circulars: "
            "https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf "
            "and https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf",
            ""
        ]
    if data.get("errors"):
        lines += ["**Data notes:** " + " | ".join(data["errors"][:4]), ""]
    if data["status"] == "INCOMPLETE EOD RESEARCH":
        lines += ["**NO NEW VERIFIED EOD PICKS.** Do not use stale or incomplete data as today's trade signal or as updated stop advice.", ""]
    if not data.get("tracking_state_restored", True) and data.get("market_date"):
        lines += ["**TRACKING CAVEAT:** Prior GitHub Actions cache was not restored; older plans may not appear. Actual broker positions cannot be inferred.", ""]
    if data["status"] == "PARTIAL EOD RESEARCH":
        lines += ["**PARTIAL COVERAGE.** Listed ideas, if any, come only from stocks with complete validated inputs. An empty list is not a market-wide no-trade conclusion.", ""]
    if data.get("shortlist_policy"):
        policy=data["shortlist_policy"]
        lines += [
            "## Daily new-idea discipline — maximum 3 combined across A, B and C",
            f"- Fresh conditional trade ideas selected: **{policy['fresh_conditional_ideas']}** (normal goal <=2, hard maximum 3, zero allowed).",
            f"- {policy['qualified_pre_shortlist']} qualified ideas before final selection; {policy['not_selected']} excluded from fresh shortlist. Past review items are separate and are NOT extra new trade calls.",
            f"- Existing research ideas under EOD review: {policy['prior_research_ideas_under_review']}; actual broker holdings: **NOT VERIFIED**. {policy['note']}",
            ""
        ]
    if data["status"] == "PARTIAL EOD RESEARCH" and not data.get("candidates"):
        covered = data.get("coverage",{}).get("valid_history_and_chain","unknown number of")
        lines += [f"**NO A-TIER TRADE AMONG {covered} FULLY COVERED STOCKS.** Incomplete names are excluded; this is NOT a complete-universe no-trade determination.", ""]
    if data["status"] == "VERIFIED EOD RESEARCH" and not data.get("candidates"):
        if data.get("expert_trade_plans"):
            lines += ["**NO A-TIER TRADE.** No stock passed all strict futures/OI/technicals/2R gates; separate lower-conviction conditional expert plans appear below.", ""]
        else:
            lines += ["**NO TRADE.** No stock passed the full futures OI, options-chain, technical-momentum and 2R risk gates. No A-tier candidate is being recommended.", ""]
    for n, c in enumerate(data.get("candidates", []), 1):
        lines += [f"## {n}. {c['symbol']} — {c['direction']} WATCH ({c['score']}/100 evidence score)",
                  f"- Futures {c['futures_expiry']}: {c['regime']}; settlement ₹{c['futures_settlement']:.2f} ({c['futures_change_pct']:+.2f}%), OI {c['futures_oi']:,.0f} ({c['futures_oi_change_pct']:+.2f}%; change {c['futures_oi_change']:+,.0f}).",
                  f"- Cash close ₹{c['cash_close']:.2f}, RVOL20 {c['cash_rvol20']:.2f}x, ATR14 ₹{c['atr14']:.2f}.",
                  f"- **Trend:** EMA20 ₹{c['ema20']:.2f}, EMA50 ₹{c['ema50']:.2f}; SMA20 ₹{c['sma20']:.2f}, SMA50 ₹{c['sma50']:.2f}. EMA cross: {c['ema_crossover'] or 'none recent'}; SMA cross: {c['sma_crossover'] or 'none recent'}.",
                  f"- **Momentum:** RSI14 {c['rsi14']:.1f}; MACD {c['macd']:+.3f}, signal {c['macd_signal']:+.3f}, histogram {c['macd_hist']:+.3f}; recent MACD cross: {c['macd_crossover'] or 'none'}.",
                  f"- **Fibonacci 60-session historical swing:** ₹{c['fib_swing_low60']:.2f}–₹{c['fib_swing_high60']:.2f}; nearby fib support ₹{c['fib_support'] if c['fib_support'] is not None else 'N/A'} / resistance ₹{c['fib_resistance'] if c['fib_resistance'] is not None else 'N/A'}. These are contextual levels, not assured reversal points.",
                  f"- **Evidence:** Futures {c['futures_score']}/40 + Options {c['options_score']}/35 + Technical {c['technical_score']}/25; confirmations: {', '.join(c['technical_reasons'])}.",
                  f"- Options expiry {c['options_expiry']}: max PE OI wall ₹{c['put_wall']:g} (previous ₹{c['previous_put_wall'] or 0:g}), max CE OI wall ₹{c['call_wall']:g} (previous ₹{c['previous_call_wall'] or 0:g}); nearest relevant walls PE ₹{c['near_put_wall'] or 0:g} / CE ₹{c['near_call_wall'] or 0:g}.",
                  f"- Full-chain max pain ₹{c['max_pain']:g} (previous ₹{c['previous_max_pain'] or 0:g}), PCR {c['pcr']:.3f} (previous {c['previous_pcr'] or 0:.3f}); PE/CE OI change {c['pe_oi_change']:+,}/{c['ce_oi_change']:+,}.",
                  f"- Option premium/OI proxies at highest walls: PE {c['put_wall_premium_proxy']['label']} (OI Δ {c['put_wall_premium_proxy']['oi_change']:+,}); CE {c['call_wall_premium_proxy']['label']} (OI Δ {c['call_wall_premium_proxy']['oi_change']:+,}). These do not establish actual writing or covering.",
                  f"- **Next-session CASH reference trigger:** ₹{c['entry_trigger']:.2f}; hard SL ₹{c['stop_loss']:.2f}; T1 ₹{c['target_1']:.2f}; T2 ₹{c['target_2']:.2f}; T3 ₹{c.get('target_3',c['target_2']):.2f} (stretch projection); modelled net T1 R:R {c['modelled_net_rr_t1']:.2f}:1 (assumed 0.15% round-trip costs).",
                  f"- Wait for confirmed 5-minute breakout/breakdown next session; do not chase an opening gap beyond ₹{c['gap_skip_level']:.2f}. Hold at most 1–5 sessions; recheck EOD OI and close. No trades are executed.",
                  ""]
    if data["status"] in ("VERIFIED EOD RESEARCH", "PARTIAL EOD RESEARCH"):
        plans = data.get("expert_trade_plans", [])
        lines += ["## B. Expert Conditional Trade Plans — structure-based T1, no forced 2R gate", "",
                  "B-tier is independent of A-tier. A plan is VALID FOR THE NEXT TWO TRADING SESSIONS ONLY, requires an unverified next-session five-minute breakout/breakdown and volume confirmation, and is NOT an automatically executable call. Strict A-tier conditions remain unchanged.", ""]
        if not plans:
            lines += ["**NO QUALIFYING B-TIER PLAN TODAY.** Expert-watch ideas below may lack safe stops, independent near-term target levels or sufficient directional confirmation.", ""]
        for n, p in enumerate(plans, 1):
            lines += [
                f"### {n}. {p['symbol']} — {p['direction']} CONDITIONAL CASH RESEARCH PLAN (B-tier)",
                f"- **Evidence:** {p['pattern']}; cash close ₹{p['cash_close']:.2f}; relative volume {p['cash_rvol20']:.2f}×. Futures {p['futures_regime']} (price {p['futures_change_pct']:+.2f}%, OI {p['futures_oi_change_pct']:+.2f}%).",
                f"- **Technicals/options:** EMA20 ₹{p['ema20']:.2f}, EMA50 ₹{p['ema50']:.2f}, RSI14 {p['rsi14']:.1f}, MACD histogram {p['macd_hist']:+.3f}; near put/call walls {p['put_wall'] or 'unavailable'} / {p['call_wall'] or 'unavailable'}, max pain {p['max_pain'] or 'unavailable'}.",
                f"- **ENTRY CASH trigger:** ₹{p['entry_trigger']:.2f} conditional on a confirmed 5-minute close beyond it + supportive volume. **STOP LOSS:** ₹{p['stop_loss']:.2f} (initial gross price risk {p['initial_risk_pct']:.2f}% before gaps/costs).",
                f"- **T1:** ₹{p['target_1']:.2f} — {p['target_sources'][0]} (modelled net {p['modelled_net_rr_t1']:.2f}R).",
                f"- **T2:** ₹{p['target_2']:.2f} — {p['target_sources'][1]} (modelled net {p['modelled_net_rr_t2']:.2f}R).",
                f"- **T3:** ₹{p['target_3']:.2f} — {p['target_sources'][2]} (modelled net {p['modelled_net_rr_t3']:.2f}R, extension only).",
                f"- **Trigger and gap discipline:** {p['entry_condition']} Do NOT chase beyond CASH ₹{p['gap_skip_level']:.2f}. Levels are not stock-futures contract prices.",
                f"- **Exit/expiry:** {p['exit_rule']}",
                f"- **What still fails strict A-tier or needs review:** {'; '.join(p['unresolved_evidence'])}. A low T1 R:R can still be unappealing after costs and hit-rate uncertainty; this is NOT an A-tier or guaranteed recommendation.",
                ""
            ]
    # These are NOT trade recommendations, and never silently replace NO TRADE.
    # They expose explicitly reasoned exceptions outside strict indicator gates.
    if data["status"] in ("VERIFIED EOD RESEARCH", "PARTIAL EOD RESEARCH"):
        c_plans=data.get("expert_c_trade_plans",[])
        lines += ["## C. Expert Opportunities — conditional plans + remaining watch-only ideas", "",
                  "C-tier is lower-conviction than A/B. An early-stage plan is issued only with an independent technical invalidation and price-structure T1; 0.6R at T1 is a net minimum, NOT a fixed mandatory target. Do not force a plan from an untradable watch.", ""]
        for n, p in enumerate(c_plans,1):
            lines += [
                f"### C{n}. {p['symbol']} — {p['direction']} CONDITIONAL CASH RESEARCH PLAN",
                f"- **Setup:** {p['pattern']}; {p['entry_pattern']}; cash close ₹{p['cash_close']:.2f}, RVOL {p['cash_rvol20']:.2f}×; futures {p['futures_regime']} (price {p['futures_change_pct']:+.2f}% / OI {p['futures_oi_change_pct']:+.2f}%).",
                f"- **Entry ₹{p['entry_trigger']:.2f} | SL ₹{p['stop_loss']:.2f} | risk {p['initial_risk_pct']:.2f}%**. A next-session 5-minute cash confirmation with volume is required and unverified; retest strategies require a real pullback. Never chase opening gaps.",
                f"- **T1 ₹{p['target_1']:.2f} | net {p['modelled_net_rr_t1']:.2f}R** — {p['target_sources'][0]}.",
                f"- **T2 ₹{p['target_2']:.2f} | net {p['modelled_net_rr_t2']:.2f}R** — {p['target_sources'][1]}.",
                f"- **T3 ₹{p['target_3']:.2f} | net {p['modelled_net_rr_t3']:.2f}R** — {p['target_sources'][2]}.",
                f"- **Illustrative R benchmarks, NOT imposed targets:** 0.6R ₹{p['rr_reference_points']['0.6R']:.2f}; 1.5R ₹{p['rr_reference_points']['1.5R']:.2f}; 3R ₹{p['rr_reference_points']['3.0R']:.2f}.",
                f"- **Evidence and caveats:** EMA20 ₹{p['ema20']:.2f}, EMA50 ₹{p['ema50']:.2f}, RSI14 {p['rsi14']:.1f}, MACD histogram {p['macd_hist']:+.4f}; PE wall {p['put_wall'] or 'unavailable'} / CE wall {p['call_wall'] or 'unavailable'}, max pain {p['max_pain'] or 'unavailable'}. {'; '.join(p['unresolved_evidence'])}.",
                f"- **Lifecycle:** Pending idea expires after {p['valid_for_next_sessions']} trading sessions; if separately confirmed filled, reassess daily for no more than {p['holding_max_sessions']} trading sessions. {p['exit_rule']}",
                ""
            ]
        ideas=data.get("expert_opportunities",[])
        lines += ["### Other C ideas — WATCH ONLY (NOT trade calls), no defensible trade plan yet", ""]
        if not ideas:
            lines += ["**No additional credible ideas today.** Nothing else met the minimum independent pattern and liquidity checks.", ""]
        for number, idea in enumerate(ideas,1):
            lines += [
                f"### {number}. {idea['symbol']} — {idea['directional_bias']} BIAS / WATCH ONLY",
                f"- **Why worth observing:** {idea['pattern']}. NSE cash close ₹{idea['cash_close']:.2f}, relative volume {idea['relative_volume']:.2f}×; futures {idea['futures_regime']} (price {idea['futures_change_pct']:+.2f}%, OI {idea['futures_oi_change_pct']:+.2f}%).",
                f"- **Technical context:** EMA20 ₹{idea['ema20']:.2f}, EMA50 ₹{idea['ema50']:.2f}, RSI14 {idea['rsi14']:.1f}, MACD histogram {idea['macd_hist']:+.3f}; put/call walls {idea['put_wall'] if idea['put_wall'] else 'unavailable'} / {idea['call_wall'] if idea['call_wall'] else 'unavailable'}.",
                f"- **What would confirm interest:** A next-session price/volume decision around cash ₹{idea['price_decision_level']:.2f}; this level is NOT an instruction to buy or sell.",
                f"- **What would invalidate it:** {'Cash reference ₹%.2f' % idea['indicative_invalidation'] if idea['indicative_invalidation'] is not None else 'No acceptable stop distance yet; do not construct a trade plan.'}",
                f"- **Why it did not become an A-tier pick / unresolved evidence:** {'; '.join(idea['caveats'])}.",
                "- **Status: WATCH ONLY, not a recommendation.** Confirm with next-session price action, options positioning and execution costs before any separate trade plan.",
                ""
            ]
    if data.get("active_plan_reviews"):
        lines += ["## D. Daily A/B/C research lifecycle review — HOLD / TIGHTEN / EXIT", "",
                  "**These are strictly IF-FILLED scenarios, not verified portfolio positions.** Price touches do not establish orders or intraday event sequencing. Revised stops are for NEXT session if adopted via broker; they were not active during the observed day. Existing A-tier positions are reviewed on the same evidence-driven schedule.", ""]
        for u in data["active_plan_reviews"]:
            lines += [f"### {u['symbol']} — {u['id']}",
                      f"- **Observed status:** {u['status']}",
                      f"- **Recommendation IF independently confirmed filled:** {u['action_if_filled']}"]
            if "latest_cash_close" in u:
                lines += [
                    f"- **Current price:** close ₹{u['latest_cash_close']:.2f} (H ₹{u['cash_high']:.2f}, L ₹{u['cash_low']:.2f}); move vs cash entry {u['price_move_from_entry_pct']:+.2f}%, not actual P&L.",
                    f"- **Risk/stop:** original ₹{u['original_stop']:.2f}; previous model stop ₹{u['prior_suggested_stop']:.2f}; proposed NEXT-session stop ₹{u['suggested_stop_next_session_if_filled']:.2f}. Never loosen if already protected tighter.",
                    f"- **Targets:** original T1/T2/T3 ₹{' / ₹'.join(f'{t:.2f}' for t in u['original_targets'])}; new conditional T1 ₹{u['updated_t1_if_filled']:.2f}. {u['target_note']}.",
                    f"- **Updated fundamentals of setup:** futures {u['futures_regime_today']} (price {u['futures_price_change_pct']:+.2f}% / OI {u['futures_oi_change_pct']:+.2f}%); EMA20 ₹{u['ema20']:.2f}, RSI14 {u['rsi14']:.1f}, MACD histogram {u['macd_hist']:+.4f}, opposing options wall {u['opposing_oi_wall'] or 'unavailable'}.",
                    f"- **Elapsed sessions:** {u['observed_sessions_since_signal']} since issue; {u['hypothetical_holding_sessions']} hypothetical holding observations. Actual trade status: {u['fill_status']}.",
                ]
            lines.append("")
    if data.get("expert_prior_updates") and not data.get("active_plan_reviews"):
        lines += ["## Prior conditional plan observations — not verified fills"]
        for u in data["expert_prior_updates"]:
            lines.append(f"- {u['id']}: {u['status']}")
        lines.append("")
    if data.get("prior_updates"):
        lines += ["## Previous A-tier research watch updates"]
        for u in data["prior_updates"]:
            lines.append(f"- {u['id']}: {u['status']}")
        lines.append("")
    lines += ["## Limitations",
              "- These are conditional research WATCH levels, **not executed orders**. Cash-equity levels are not futures execution prices.",
              "- OI buildup/covering is inferred from price and net OI, not direct identification of buyers/writers.",
              "- Put/call walls, Fibonacci levels, EMA/SMA, RSI and MACD are related proxies, not independent guarantees or targets; test historical performance before relying on any combination. Exchange prices may be corrected.",
              "- Positions are **not monitored intraday**. Daily OHLC does not establish order/stop sequence or a five-minute breakout close. For any actual trade, arrange broker-side stop protection; overnight gaps may exceed SL.",
              "- B/C T1 is structure-based, not chosen solely to fit an R ratio. C's 0.6R minimum net T1 is NOT evidence of a profitable strategy; a single 0.6R full exit needs over 62.5% winners before costs.",
              "- The 0.15% round-trip impact assumption is illustrative, not account-specific brokerage/taxes. Evidence scores are heuristics, not success probabilities.",
              "- Futures and options prices include expiry/basis risks; evaluate appropriate instrument separately before execution.",
              ""]
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", default=None, help="Override IST market date YYYY-MM-DD for offline/backfill tests")
    parser.add_argument("--history-days",type=int,default=115)
    parser.add_argument("--state",default="nse_eod_state.json")
    args = parser.parse_args()
    today = date.fromisoformat(args.asof) if args.asof else datetime.now(IST).date()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    result = {"generated_ist":datetime.now(IST).isoformat(timespec="seconds"),
              "requested_date":today.isoformat(),"market_date":None,
              "status":"NO VERIFIED TRADE", "data_source":EOD_SOURCE,
              "candidates":[],"expert_trade_plans":[],"expert_c_trade_plans":[],
              "expert_opportunities":[],"active_plan_reviews":[],
               "prior_updates":[],"expert_prior_updates":[],"errors":[]}
    closure = market_closure(today)
    if closure:
        # A market holiday is not a failed NSE download and must never
        # trigger a stale-data recovery scan or fabricated no-trade signal.
        result["status"] = "MARKET HOLIDAY"
        result["holiday_reason"] = closure
        OUTPUT.joinpath("report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        OUTPUT.joinpath("report.md").write_text(render(result), encoding="utf-8")
        print(f"RESULT status=MARKET HOLIDAY requested_date={today} reason={closure}")
        return 0
    state_path = Path(args.state)
    previous = {}
    result["tracking_state_restored"] = False
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            result["tracking_state_restored"] = True
        except (ValueError,OSError): result["errors"].append("Prior watch state could not be read")
    try:
        market_date,fo,cm,errors=most_recent(today)
        result["market_date"]=market_date.isoformat()
        result["fetch_notes"]=errors
        if market_date != today:
            result["errors"].append(f"Today's official EOD archive not available; latest validated: {market_date}")
        else:
            hist,missing=cash_history(market_date,days=args.history_days)
            result["history_sessions"]=len(hist)
            result["cash_history_missing_days"]=len(missing)
            result["cash_history_errors"]=missing
            stocks=equity_rows(cm)
            prior,keep=track_prior(previous.get("active",[]),market_date,stocks)
            result["prior_updates"]=prior
            picks,plans,c_plans,expert_ideas,watch,coverage,regimes,nf,snapshots=build_market_summary(market_date,fo,cm,hist)
            expert_prior, expert_keep = review_research_plans(
                previous.get("expert_active",[]), market_date, stocks, snapshots)
            result["expert_prior_updates"] = expert_prior
            result["active_plan_reviews"] = expert_prior
            # Do not reissue a fresh idea for a name already under review.
            active_symbols = {item["signal"]["symbol"] for item in expert_keep}
            plans = [p for p in plans if p["symbol"] not in active_symbols]
            c_plans = [p for p in c_plans if p["symbol"] not in active_symbols]
            expert_ideas = [w for w in expert_ideas if w["symbol"] not in active_symbols]
            picks,plans,c_plans,selection_policy=choose_daily_shortlist(
                picks,plans,c_plans,active_research=expert_keep)
            result["shortlist_policy"]=selection_policy
            result.update({"candidates":picks, "expert_trade_plans":plans,
                           "expert_c_trade_plans":c_plans,
                           "expert_opportunities":expert_ideas, "other_observations":watch,
                           "coverage":coverage,"futures_regimes":regimes,
                           "stock_futures_symbols":nf})
            result["status"]="VERIFIED EOD RESEARCH"
            apply_coverage_status(result)
            current = [{"asof_date":market_date.isoformat(),"signal":pick} for pick in picks]
            deduped = {item["signal"]["signal_id"]: item for item in (keep + current)}
            new_expert = [{"asof_date":market_date.isoformat(), "last_checked":market_date.isoformat(),
                           "observed_sessions":0, "signal":plan} for plan in (picks+plans+c_plans)
                           if plan["symbol"] not in active_symbols]
            expert_deduped = {item["signal"]["signal_id"]:item for item in (expert_keep+new_expert)}
            state_path.write_text(json.dumps({"last_date":market_date.isoformat(),
                                              "active":list(deduped.values())[-25:],
                                              "expert_active":list(expert_deduped.values())[-25:]},indent=2),encoding="utf-8")
    except (Unavailable, ValueError, OSError) as exc:
        result["errors"].append(str(exc)[:900])
    OUTPUT.joinpath("report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    OUTPUT.joinpath("report.md").write_text(render(result),encoding="utf-8")
    print(f"RESULT status={result['status']} market_date={result['market_date']} strict_candidates={len(result['candidates'])} expert_plans={len(result['expert_trade_plans'])} expert_c_plans={len(result['expert_c_trade_plans'])} expert_watch={len(result['expert_opportunities'])} active_reviews={len(result['active_plan_reviews'])} errors={len(result['errors'])}")
    print(f"COVERAGE={result.get('coverage',{})}")
    print(f"FRESH_SHORTLIST={result.get('shortlist_policy',{})}")
    print(f"FUTURES_REGIMES={result.get('futures_regimes',{})}")
    if result["errors"]: print("NOTES:", " | ".join(result["errors"][:2]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())


