#!/usr/bin/env python3
"""One-shot NSE EOD futures/options positional research. NEVER places broker orders."""
from __future__ import annotations
import argparse
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from data import Unavailable, cash_history, most_recent, url_for
from logic import chain_metrics, expiry, num, research_candidate, tech_metrics, classify_futures, pct

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
    return picks[:3], regime_observations[:5], dict(covered), dict(regimes), len(futures)

def track_prior(prior, current_date, cash):
    updates, kept = [], []
    for previous in prior or []:
        try:
            last = date.fromisoformat(previous["asof_date"])
            sig = previous["signal"]
            symbol, direction = sig["symbol"], sig["direction"]
            sl, entry, t1, t2 = [float(sig[k]) for k in ("stop_loss","entry_trigger","target_1","target_2")]
            if (current_date-last).days > 8: continue
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

def render(data):
    lines = [f"# FnO Tattva — NSE EOD OI Research | {data['market_date'] or data['requested_date']}",
             "", f"**Status:** {data['status']}", f"**Generated:** {data['generated_ist']}",
             f"**Source:** {EOD_SOURCE}", ""]
    if data.get("market_date"):
        day = date.fromisoformat(data["market_date"])
        lines += [f"- FO archive: {url_for('FO', day)}", f"- CM archive: {url_for('CM', day)}", ""]
    if data.get("errors"):
        lines += ["**Data notes:** " + " | ".join(data["errors"][:4]), ""]
    if data["status"] != "VERIFIED EOD RESEARCH":
        lines += ["**NO NEW VERIFIED EOD PICKS.** Do not use stale or incomplete data as today's trade signal.", ""]
    for n, c in enumerate(data.get("candidates", []), 1):
        lines += [f"## {n}. {c['symbol']} — {c['direction']} WATCH ({c['score']}/100 evidence score)",
                  f"- Futures {c['futures_expiry']}: {c['regime']}; settlement ₹{c['futures_settlement']:.2f} ({c['futures_change_pct']:+.2f}%), OI {c['futures_oi']:,.0f} ({c['futures_oi_change_pct']:+.2f}%; change {c['futures_oi_change']:+,.0f}).",
                  f"- Spot close ₹{c['cash_close']:.2f}; relative volume {c['cash_rvol20']:.2f}x, EMA20 ₹{c['ema20']:.2f}, ATR14 ₹{c['atr14']:.2f}.",
                  f"- Options expiry {c['options_expiry']}: max PE OI wall ₹{c['put_wall']:g} (previous ₹{c['previous_put_wall'] or 0:g}), max CE OI wall ₹{c['call_wall']:g} (previous ₹{c['previous_call_wall'] or 0:g}); nearest relevant walls PE ₹{c['near_put_wall'] or 0:g} / CE ₹{c['near_call_wall'] or 0:g}.",
                  f"- Full-chain max pain ₹{c['max_pain']:g} (previous ₹{c['previous_max_pain'] or 0:g}), PCR {c['pcr']:.3f} (previous {c['previous_pcr'] or 0:.3f}); PE/CE OI change {c['pe_oi_change']:+,}/{c['ce_oi_change']:+,}.",
                  f"- **Next-session CASH reference trigger:** ₹{c['entry_trigger']:.2f}; hard SL ₹{c['stop_loss']:.2f}; T1 ₹{c['target_1']:.2f}; T2 ₹{c['target_2']:.2f}; modelled net T1 R:R {c['modelled_net_rr_t1']:.2f}:1 (assumed 0.15% round-trip costs).",
                  f"- Wait for confirmed 5-minute breakout/breakdown next session; do not chase an opening gap beyond ₹{c['gap_skip_level']:.2f}. Hold at most 1–5 sessions; recheck EOD OI and close. No trades are executed.",
                  ""]
    if data.get("prior_updates"):
        lines += ["## Previous research watch updates"]
        for u in data["prior_updates"]:
            lines.append(f"- {u['id']}: {u['status']}")
        lines.append("")
    lines += ["## Limitations",
              "- These are conditional research WATCH levels, **not executed orders**. Cash-equity levels are not futures execution prices.",
              "- OI buildup/covering is inferred from price and net OI, not direct identification of buyers/writers.",
              "- Put/call walls and max pain are not guaranteed barriers or targets. Closing prices may change after exchange corrections.",
              "- Positions are **not monitored intraday**. Daily OHLC does not establish order/stop sequence or a five-minute breakout close. For any actual trade, arrange broker-side stop protection; overnight gaps may exceed SL.",
              "- The 0.15% round-trip impact assumption is illustrative, not account-specific brokerage/taxes. Evidence scores are heuristics, not success probabilities.",
              "- Futures and options prices include expiry/basis risks; evaluate appropriate instrument separately before execution.",
              ""]
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", default=None, help="Override IST market date YYYY-MM-DD for offline/backfill tests")
    parser.add_argument("--history-days",type=int,default=47)
    parser.add_argument("--state",default="nse_eod_state.json")
    args = parser.parse_args()
    today = date.fromisoformat(args.asof) if args.asof else datetime.now(IST).date()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    result = {"generated_ist":datetime.now(IST).isoformat(timespec="seconds"),
              "requested_date":today.isoformat(),"market_date":None,
              "status":"NO VERIFIED TRADE", "data_source":EOD_SOURCE,
              "candidates":[],"prior_updates":[],"errors":[]}
    state_path = Path(args.state)
    previous = {}
    if state_path.exists():
        try: previous = json.loads(state_path.read_text(encoding="utf-8"))
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
            stocks=equity_rows(cm)
            prior,keep=track_prior(previous.get("active",[]),market_date,stocks)
            result["prior_updates"]=prior
            picks,watch,coverage,regimes,nf=build_market_summary(market_date,fo,cm,hist)
            result.update({"candidates":picks, "other_observations":watch,
                           "coverage":coverage,"futures_regimes":regimes,
                           "stock_futures_symbols":nf})
            result["status"]="VERIFIED EOD RESEARCH"
            current = [{"asof_date":market_date.isoformat(),"signal":pick} for pick in picks]
            state_path.write_text(json.dumps({"last_date":market_date.isoformat(),
                                              "active":(keep+current)[-25:]},indent=2),encoding="utf-8")
    except (Unavailable, ValueError, OSError) as exc:
        result["errors"].append(str(exc)[:900])
    OUTPUT.joinpath("report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    OUTPUT.joinpath("report.md").write_text(render(result),encoding="utf-8")
    print(f"RESULT status={result['status']} market_date={result['market_date']} candidates={len(result['candidates'])} errors={len(result['errors'])}")
    print(f"COVERAGE={result.get('coverage',{})}")
    print(f"FUTURES_REGIMES={result.get('futures_regimes',{})}")
    if result["errors"]: print("NOTES:", " | ".join(result["errors"][:2]))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
