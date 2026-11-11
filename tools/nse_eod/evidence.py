"""Auditable EOD cash-price and same-contract futures/options history.

Uses only official dated NSE UDiFF CM and FO bhavcopy archives already validated
by data.load. No paid API, no broker access, no unverified news narratives.

Cash path covers the prior research idea's life within available CM lookback.
FO history is bounded to five prior validated NSE sessions, plus current FO;
rollover/expiry changes are never silently spliced across contracts.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from math import isfinite

from data import Unavailable, load, url_for
from logic import chain_metrics, classify_futures, expiry, num, pct

FO_LOOKBACK_SESSIONS = 5
CASH_PATH_SESSIONS = 20


def _valid(value):
    try:
        n = float(value)
        return n if isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None


def _cash_symbol_rows(rows, interested):
    out = {}
    for row in rows or []:
        sym = row.get("TckrSymb")
        if sym not in interested or row.get("SctySrs", "EQ") != "EQ":
            continue
        o,h,l,c,v = [_valid(row.get(k)) for k in
                     ("OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol")]
        if not all((o,h,l,c,v)) or not l <= min(o,c) <= max(o,c) <= h:
            continue
        if sym not in out or v > _valid(out[sym].get("TtlTradgVol") or 0):
            out[sym]=row
    return out


def build_cash_paths(history, today, today_rows, prior, max_days=CASH_PATH_SESSIONS):
    """Chronological OHLCV per tracked stock, with official archive provenance."""
    symbols = {r.get("signal",{}).get("symbol") for r in prior or []}
    symbols.discard(None)
    if not symbols:
        return {}
    records = defaultdict(list)
    dates = sorted(d for d in history if d <= today)
    if today not in dates:
        dates.append(today)
    for session in dates:
        rows = today_rows if session == today else history.get(session)
        for sym,bar in _cash_symbol_rows(rows,symbols).items():
            records[sym].append({
                "date":session.isoformat(),"open":round(num(bar.get("OpnPric")),2),
                "high":round(num(bar.get("HghPric")),2),
                "low":round(num(bar.get("LwPric")),2),
                "close":round(num(bar.get("ClsPric")),2),
                "cash_volume":round(num(bar.get("TtlTradgVol"))),
                "cm_source":url_for("CM",session),
            })
    return {sym:series[-max_days:] for sym,series in records.items()}


def price_path_evidence(signal, trail):
    """Describe touched price levels and price excursions, not executed trades.

    Same-candle stop/target collisions are explicitly ambiguous; EOD cannot
    establish the five-minute entry condition or realized P&L.
    """
    if not trail:
        return {"status":"UNVERIFIED: NO DATED CASH PRICE HISTORY",
                "observed_sessions":0,"entry_confirmed":False,"fills_known":False}
    side = 1 if signal.get("direction")=="LONG" else -1
    entry = _valid(signal.get("entry_trigger"))
    stop = _valid(signal.get("stop_loss"))
    t1,t2,t3 = (_valid(signal.get("target_"+str(n))) for n in (1,2,3))
    if not all((entry,stop,t1,t2,t3)) or side*(entry-stop)<=0:
        return {"status":"INVALID PRIOR SIGNAL LEVELS",
                "observed_sessions":0,"entry_confirmed":False,"fills_known":False}
    issued=signal.get("market_date")
    eligible=[bar for bar in trail if bar["date"]>str(issued)]
    hits={"entry":[],"stop":[],"T1":[],"T2":[],"T3":[]}
    collision_days=[]
    trigger_day=None
    for bar in eligible:
        hi,lo=bar["high"],bar["low"]
        entry_touched=hi>=entry if side>0 else lo<=entry
        if "pullback" in str(signal.get("entry_pattern","")).lower():
            entry_touched=entry_touched and lo<=entry<=hi
        levels={"entry":entry_touched,
                "stop":lo<=stop if side>0 else hi>=stop,
                "T1":hi>=t1 if side>0 else lo<=t1,
                "T2":hi>=t2 if side>0 else lo<=t2,
                "T3":hi>=t3 if side>0 else lo<=t3}
        for label,yes in levels.items():
            if yes: hits[label].append(bar["date"])
        if entry_touched and trigger_day is None:
            trigger_day=bar["date"]
        if (entry_touched and levels["stop"]) or (
            levels["stop"] and any(levels[f"T{n}"] for n in (1,2,3))
        ):
            collision_days.append(bar["date"])
    after=[b for b in eligible if trigger_day and b["date"]>=trigger_day]
    # Compare observation windows without claiming a triggered broker trade.
    # Once EOD high/low possibly crossed trigger, closing prices for horizons
    # 5/7/10/15 provide counterfactual cash-price paths ONLY. Never claim
    # targets/stops actually filled or compare gross horizons as strategy P&L.
    horizons={}
    for n in (5,7,10,15):
        if len(after)>=n:
            last=after[n-1]
            horizons[str(n)]={
                "status":"OBSERVED CASH CLOSE — NOT REALIZED P&L",
                "date":last["date"],"close":last["close"],
                "gross_cash_move_pct":round(100*side*(last["close"]-entry)/entry,2),
                "gross_cash_R_vs_reference_entry":round(
                    side*(last["close"]-entry)/abs(entry-stop),2),
                "cm_source":last["cm_source"],
                "stop_touched_anytime_to_horizon":any(
                    (row["low"]<=stop if side>0 else row["high"]>=stop)
                    for row in after[:n]),
                "t3_touched_anytime_to_horizon":any(
                    (row["high"]>=t3 if side>0 else row["low"]<=t3)
                    for row in after[:n]),
            }
        else:
            horizons[str(n)]={
                "status":"INSUFFICIENT COMPLETED NSE SESSIONS",
                "observed_so_far":len(after),
                "needed":n,
            }
    large_unadjusted_jumps=[]
    for first,second in zip(trail,trail[1:]):
        if first["close"]>0:
            close_pct=100*(second["close"]/first["close"]-1)
            if abs(close_pct)>=20:
                large_unadjusted_jumps.append({
                    "date":second["date"],"raw_close_to_close_pct":round(close_pct,2),
                    "warning":"Investigate stock split/bonus/adjustment versus actual price gap before return comparisons",
                })
    if after:
        best = max(side*(b["high"]-entry) if side>0 else
                   side*(b["low"]-entry) for b in after)
        worst=min(side*(b["low"]-entry) if side>0 else
                  side*(b["high"]-entry) for b in after)
        r=abs(entry-stop)
        mfe,mae=round(best/r,2),round(worst/r,2)
    else:
        mfe=mae=None
    return {
        "status":"EOD PRICE LEVEL OBSERVATIONS ONLY — NOT VERIFIED TRADE",
        "observed_sessions":len(eligible),
        "first_observed_entry_touch":trigger_day,
        "latest_eod_date":eligible[-1]["date"] if eligible else None,
        "level_first_touch_dates":{k:(dates[0] if dates else None)
                                   for k,dates in hits.items()},
        "entry_and_stop_same_day_ambiguity":collision_days,
        "max_favourable_excursion_R_observed":mfe,
        "max_adverse_excursion_R_observed":mae,
        "history_sessions_returned":len(trail),
        "horizon_cash_close_observations_5_7_10_15":horizons,
        "corporate_action_or_gap_checks":large_unadjusted_jumps,
        "historical_cash_prices_adjusted_for_corporate_actions":False,
        "cm_archive_sources": [b["cm_source"] for b in eligible[-5:]],
        "entry_confirmed":False,
        "fills_known":False,
        "intraday_sequence_known":False,
        "method":"Dated NSE CM OHLCV; excursions measured from hypothetical CASH trigger, no slippage or fills",
    }


def _fo_snapshot(symbol, fo_rows, asof, matching_expiry, cash_close):
    """Use the SAME contract expiry as current front contract; no roll splice."""
    futures=[r for r in fo_rows
             if r.get("FinInstrmTp")=="STF" and r.get("TckrSymb")==symbol
             and expiry(r)==matching_expiry]
    if not futures:
        return {"date":asof.isoformat(),"status":"SAME-EXPIRY FUTURE MISSING",
                "fo_archive":url_for("FO",asof)}
    fut=max(futures,key=lambda x:num(x.get("TtlTradgVol")))
    oi=num(fut.get("OpnIntrst"))
    delta=num(fut.get("ChngInOpnIntrst"))
    prior_oi=oi-delta
    settle=num(fut.get("SttlmPric")) or num(fut.get("ClsPric"))
    prior_settle=num(fut.get("PrvsClsgPric"))
    if not min(oi,prior_oi,settle,prior_settle)>0:
        return {"date":asof.isoformat(),"status":"INVALID SAME-EXPIRY FUTURES OI/PRICE",
                "fo_archive":url_for("FO",asof)}
    options=[r for r in fo_rows if r.get("FinInstrmTp")=="STO"
             and r.get("TckrSymb")==symbol and expiry(r)==matching_expiry]
    chain=chain_metrics(options,cash_close) if options else None
    change=pct(settle,prior_settle)
    oi_change=pct(oi,prior_oi)
    return {
        "date":asof.isoformat(),"status":"VERIFIED NSE FO EOD",
        "contract_expiry":matching_expiry.isoformat(),
        "futures_settlement":round(settle,2),"futures_change_pct":round(change,2),
        "futures_oi":round(oi),"futures_oi_change_pct":round(oi_change,2),
        "futures_regime":classify_futures(change,oi_change),
        "same_expiry_options_chain":bool(chain),
        "pcr":chain.get("pcr") if chain else None,
        "max_pain":chain.get("max_pain") if chain else None,
        "put_wall":chain.get("near_put_wall") if chain else None,
        "call_wall":chain.get("near_call_wall") if chain else None,
        "put_oi_change":chain.get("pe_oi_change") if chain else None,
        "call_oi_change":chain.get("ce_oi_change") if chain else None,
        "fo_archive":url_for("FO",asof),
    }


def fetch_fo_evidence(prior, history, asof, current_fo, snapshots, cash_paths,
                      loader=load, lookback=FO_LOOKBACK_SESSIONS):
    """Download bounded additional official FO archives for active ideas.

    Fallback to a partial recent derivatives trail when one or more archives
    are missing. Never insert synthetic observations or silently roll a future.
    Historical FO loading occurs ONLY when there are older plans to reassess.
    """
    symbols={r.get("signal",{}).get("symbol") for r in prior or []}
    symbols.discard(None)
    if not symbols:
        return {},{"historical_fo_requested":0,"historical_fo_downloaded":0,
                   "missing":{},"scope":"none: no earlier tracked research"}
    days=sorted(d for d in history if d<asof)[-lookback:]
    downloaded={}
    errors={}
    def get(day):
        return day,loader("FO",day)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(get,day):day for day in days}
        for work in as_completed(tasks):
            day=tasks[work]
            try:
                fetched,rows=work.result()
                downloaded[fetched]=rows
            except (Unavailable,ValueError,OSError) as exc:
                errors[day.isoformat()]=str(exc)[:150]
    downloaded[asof]=current_fo
    output={}
    for sym in sorted(symbols):
        current=snapshots.get(sym) or {}
        future=current.get("future") or {}
        contract=expiry(future)
        cash_closes={date.fromisoformat(x["date"]):x["close"]
                     for x in cash_paths.get(sym,[])}
        if contract==date.min:
            output[sym]=[{"date":asof.isoformat(),
                          "status":"CURRENT SAME-EXPIRY CONTRACT UNVERIFIED"}]
            continue
        path=[]
        for day,rows in sorted(downloaded.items()):
            close=cash_closes.get(day)
            if not close:
                path.append({"date":day.isoformat(),"status":"CASH HISTORY MISSING",
                             "fo_archive":url_for("FO",day)})
                continue
            path.append(_fo_snapshot(sym,rows,day,contract,close))
        output[sym]=path
    return output,{
        "historical_fo_requested":len(days),
        "historical_fo_downloaded":len(downloaded)-1,
        "missing":errors,
        "scope":"same current front-contract expiry only; five prior NSE sessions plus current",
        "current_day":asof.isoformat(),
    }


def derivatives_evidence(trail):
    """Expose actual multi-day FO continuity, OI trends and wall shifts."""
    valid=[row for row in trail or [] if row.get("status")=="VERIFIED NSE FO EOD"]
    if not valid:
        return {"status":"NO VERIFIED FO SERIES","days":0,
                "history":[*trail][-6:]}
    regime_counts={}
    for row in valid:
        regime=row["futures_regime"]
        regime_counts[regime]=regime_counts.get(regime,0)+1
    latest=valid[-1]
    first=valid[0]
    return {
        "status":"VERIFIED FO HISTORY" if len(valid)>1 else "SINGLE FO SESSION ONLY",
        "days":len(valid),
        "first_date":first["date"],"last_date":latest["date"],
        "same_contract_expiry":latest["contract_expiry"],
        "settlement_change_over_observed_pct":round(
            100*(latest["futures_settlement"]/first["futures_settlement"]-1),2
        ) if first["futures_settlement"]>0 else None,
        "oi_change_over_observed_pct":round(
            100*(latest["futures_oi"]/first["futures_oi"]-1),2
        ) if first["futures_oi"]>0 else None,
        "latest_pcr":latest.get("pcr"),
        "latest_near_put_wall":latest.get("put_wall"),
        "latest_near_call_wall":latest.get("call_wall"),
        "regimes":regime_counts,
        "history":[*trail][-6:],
        "rollover_warning":"Past futures with different expiry are not combined or imputed",
    }
