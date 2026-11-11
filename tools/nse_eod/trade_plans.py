"""Secondary, level-based CONDITIONAL NSE cash-equity research plans.

Separate from the strict A-tier >=2R engine. No execution, intraday confirmation,
future-price translation, verified fills or statistically calibrated forecasts.
"""
from __future__ import annotations

from datetime import date
from math import isfinite


def _positive(value):
    try:
        x = float(value)
        return x if isfinite(x) and x > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def expert_trade_plan(idea, tech, chain, future=None):
    """Create a B-tier plan only if a credible T1 barrier and technical stop exist.

    No fixed 2R gate; T1 is BEFORE the nearest independently observed opposing
    price structure or option wall. No structural T1 => retain WATCH ONLY.
    """
    if not idea or not chain or idea.get("pattern_priority", 0) < 3:
        return None
    direction = idea.get("directional_bias")
    if direction not in ("LONG", "SHORT"):
        return None
    side = 1 if direction == "LONG" else -1
    regime = idea.get("futures_regime", "UNVERIFIED")
    if regime in ("UNVERIFIED", "LONG UNWINDING" if side > 0 else "SHORT COVERING"):
        return None
    if side > 0 and regime == "SHORT BUILDUP" or side < 0 and regime == "LONG BUILDUP":
        return None
    close, atr = _positive(tech.get("close")), _positive(tech.get("atr14"))
    entry = _positive(idea.get("price_decision_level"))
    stop = _positive(idea.get("indicative_invalidation"))
    if not min(close, atr, entry, stop) or side * (entry - stop) <= 0:
        return None
    rvol = _positive(idea.get("relative_volume"))
    if rvol < 1.35:
        return None
    if regime not in ("LONG BUILDUP", "SHORT BUILDUP") and (idea.get("pattern_priority") < 4 or rvol < 1.5):
        return None
    ema20 = _positive(tech.get("ema20"))
    rsi = _positive(tech.get("rsi14"))
    hist = float(tech.get("macd_hist") or 0)
    # Some A-tier trend gates may fail, but do not issue a B-tier plan against
    # both the current directional EMA20 and MACD histogram.
    if not ema20 or side * (close - ema20) <= 0 or side * hist <= 0:
        return None
    if not (42 <= rsi <= 77 if side > 0 else 23 <= rsi <= 58):
        return None
    future_underlying = _positive((future or {}).get("UndrlygPric"))
    if future_underlying and abs(future_underlying-close)/close > .025:
        return None
    risk = abs(entry - stop)
    if not (.003 <= risk/entry <= .045) or risk < .3 * atr:
        return None
    # Option positioning is a *possible* barrier, not a guaranteed reversal.
    # Previous-session price highs/lows and the completed-history fib swing
    # provide a second structural source. Max pain is contextual, not T1 by itself.
    raw = []
    def offer(name, value):
        level = _positive(value)
        if level and side*(level-entry) > .05*atr:
            raw.append((level, name))
    if side > 0:
        offer("opposing call-OI wall", chain.get("near_call_wall"))
        offer("prior 5-session high", tech.get("prev5_high"))
        offer("prior 20-session high", tech.get("prev20_high"))
        offer("prior 60-session swing high", tech.get("fib_swing_high60"))
    else:
        offer("opposing put-OI wall", chain.get("near_put_wall"))
        offer("prior 5-session low", tech.get("prev5_low"))
        offer("prior 20-session low", tech.get("prev20_low"))
        offer("prior 60-session swing low", tech.get("fib_swing_low60"))
    for name, level in (tech.get("fib_levels60") or {}).items():
        offer("prior-60-session Fibonacci " + str(name), level)
    if not raw:
        return None
    raw.sort(key=lambda item: side*(item[0]-entry))
    deduped = []
    for level, label in raw:
        if not deduped or abs(level-deduped[-1][0]) > .12*atr:
            deduped.append((level,label))
    # Place the T1 exit marginally *before*, rather than beyond, resistance/support.
    buffer = max(.05*atr, entry*.0005)
    t1 = deduped[0][0]-side*buffer
    cost = .0015*entry
    net_rr = lambda target: (side*(target-entry)-cost)/(risk+cost)
    if side*(t1-entry) <= 0 or net_rr(t1) < .75 or abs(t1-entry)/entry > .085:
        return None
    targets = [t1]
    sources = [deduped[0][1]+" (level-based)"]
    for level,label in deduped[1:]:
        aim = level-side*buffer
        if side*(aim-targets[-1]) >= max(.35*risk, .2*atr):
            targets.append(aim)
            sources.append(label+" (level-based)")
        if len(targets) >= 3:
            break
    while len(targets) < 3:
        # Only T1 is guaranteed to have independent structural evidence.
        # Clearly flag T2/T3 when they are conditional ATR/risk extensions.
        aim = targets[-1] + side*max(.75*atr, .6*risk)
        targets.append(aim)
        sources.append("conditional ATR/risk extension (not verified resistance/support)")
    if len(set(round(t, 2) for t in targets)) != 3 or any(side*(t-entry) <= 0 for t in targets):
        return None
    gap = entry+side*.5*atr
    signal_id = idea["id"].replace("-EXPERT", "-EXPERTPLAN")
    return {
        "signal_id": signal_id, "symbol": idea["symbol"], "direction": direction,
        "tier": "B — CONDITIONAL EXPERT TRADE PLAN", "market_date": idea["market_date"],
        "pattern": idea["pattern"], "pattern_priority": idea["pattern_priority"],
        "cash_close": idea["cash_close"], "cash_rvol20": idea["relative_volume"],
        "futures_regime": regime, "futures_change_pct": idea["futures_change_pct"],
        "futures_oi_change_pct": idea["futures_oi_change_pct"],
        "ema20": idea["ema20"], "ema50": idea["ema50"],
        "rsi14": idea["rsi14"], "macd_hist": idea["macd_hist"],
        "put_wall": idea.get("put_wall"), "call_wall": idea.get("call_wall"),
        "max_pain": idea.get("max_pain"),
        "entry_trigger": round(entry,2), "stop_loss": round(stop,2),
        "target_1": round(targets[0],2), "target_2": round(targets[1],2),
        "target_3": round(targets[2],2),
        "target_sources": sources,
        "modelled_net_rr_t1": round(net_rr(targets[0]),2),
        "modelled_net_rr_t2": round(net_rr(targets[1]),2),
        "modelled_net_rr_t3": round(net_rr(targets[2]),2),
        "initial_risk_pct": round(100*risk/entry,2),
        "modelled_roundtrip_cost_pct": .15,
        "gap_skip_level": round(gap,2), "valid_for_next_sessions": 2,
        "entry_condition": "Only after a next-session 5-minute CASH candle closes beyond trigger with supporting cash volume; recheck OI/news, spread and gap. The EOD engine CANNOT verify this.",
        "exit_rule": "Hard stop after confirmed entry; consider partial exits at T1/T2, never assume breakeven stop fills; close/reassess after two subsequent trading sessions or material opposite signal.",
        "unresolved_evidence": idea.get("caveats", []),
        "data_quality": idea.get("data_quality"),
        "not_a_tier_a": True, "no_orders_placed": True,
        "underlying": "NSE CASH reference, not stock-futures contract execution price",
    }


def track_expert_plans(prior, current_date, cash):
    """Track conditional plans by observed EOD sessions; never infer fills.

    A same-day rerun must not count as a new session. OHLC cannot establish
    five-minute trigger confirmation, order of stop/target touches, or profits.
    """
    updates, kept = [], []
    for item in prior or []:
        try:
            signal = item["signal"]
            issued = date.fromisoformat(item["asof_date"])
            last = date.fromisoformat(item.get("last_checked",item["asof_date"]))
            if current_date <= last:
                kept.append(item)
                continue
            if current_date < issued:
                continue
            symbol = signal["symbol"]
            row = cash.get(symbol)
            if not row:
                kept.append(item)
                updates.append({"id":signal["signal_id"],"status":"UNVERIFIED: CURRENT CASH EOD PRICE MISSING"})
                continue
            high = _positive(row.get("HghPric"))
            low = _positive(row.get("LwPric"))
            close = _positive(row.get("ClsPric"))
            if min(high,low,close) <= 0 or high < low:
                kept.append(item)
                updates.append({"id":signal["signal_id"],"status":"UNVERIFIED: INVALID CASH EOD PRICE"})
                continue
            sign = 1 if signal["direction"]=="LONG" else -1
            entry,stop = float(signal["entry_trigger"]), float(signal["stop_loss"])
            targets = [float(signal["target_"+str(i)]) for i in (1,2,3)]
            entry_touched = high>=entry if sign>0 else low<=entry
            stop_touched = low<=stop if sign>0 else high>=stop
            target_touched = [high>=t if sign>0 else low<=t for t in targets]
            if entry_touched and stop_touched:
                status = "ENTRY AND SL LEVELS BOTH TOUCHED; ORDER/FILL UNKNOWN"
            elif stop_touched:
                status = "STOP/INVALIDATION LEVEL TOUCHED; ENTRY UNCONFIRMED"
            elif any(target_touched):
                ix = max(i for i,v in enumerate(target_touched) if v)+1
                status = f"T{ix} LEVEL TOUCHED; ENTRY/5-MIN CONFIRMATION UNVERIFIED"
            elif entry_touched:
                status = "ENTRY LEVEL TOUCHED; 5-MIN CONFIRMATION UNVERIFIED"
            else:
                status = "NOT TRIGGERED IN EOD HIGH/LOW"
            count = int(item.get("observed_sessions",0))+1
            updates.append({"id":signal["signal_id"],"status":status,
                            "cash_close":round(close,2), "observed_sessions":count,
                            "asof":current_date.isoformat()})
            if count < int(signal.get("valid_for_next_sessions",2)) and not stop_touched:
                kept.append({**item,"last_checked":current_date.isoformat(),
                             "observed_sessions":count})
        except (TypeError,ValueError,KeyError):
            continue
    return updates, kept
