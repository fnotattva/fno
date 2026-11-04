"""Pure NSE futures/options EOD research calculations; no broker and no orders."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite
from technicals import compute_technicals, technical_confirmation

def num(v, default=0.0):
    try:
        n = float(str(v or "").replace(",", ""))
        return n if isfinite(n) else default
    except (ValueError, TypeError):
        return default

def pct(now, before):
    return 100.0 * (now / before - 1) if before > 0 else 0.0

def expiry(row):
    try: return date.fromisoformat(row["XpryDt"][:10])
    except (ValueError, KeyError, TypeError): return date.min

def max_pain(rows):
    """Linear scan of sorted strikes using call prefixes and put suffixes."""
    values = defaultdict(lambda: {"CE": 0.0, "PE": 0.0})
    for row in rows:
        side = row.get("OptnTp", "")
        strike = num(row.get("StrkPric"))
        oi = num(row.get("OpnIntrst"))
        if side in ("CE", "PE") and strike > 0 and oi > 0:
            values[strike][side] += oi
    strikes = sorted(values)
    if len(strikes) < 12:
        return None
    ce_total = sum(values[k]["CE"] for k in strikes)
    pe_total = sum(values[k]["PE"] for k in strikes)
    if not ce_total or not pe_total: return None
    put_oi_ahead = pe_total
    put_weight_ahead = sum(k * values[k]["PE"] for k in strikes)
    call_oi_behind = call_weight_behind = 0.0
    best_strike = None
    lowest_payout = float("inf")
    for k in strikes:
        put_oi_ahead -= values[k]["PE"]
        put_weight_ahead -= k * values[k]["PE"]
        payout = k * call_oi_behind - call_weight_behind + put_weight_ahead - k * put_oi_ahead
        if payout < lowest_payout:
            best_strike, lowest_payout = k, payout
        call_oi_behind += values[k]["CE"]
        call_weight_behind += k * values[k]["CE"]
    return {"strike": best_strike, "payout_price_units": round(lowest_payout, 3)}

def classify_futures(price_change_pct, oi_change_pct, epsilon_price=0.05, epsilon_oi=0.5):
    if abs(price_change_pct) < epsilon_price or abs(oi_change_pct) < epsilon_oi:
        return "NEUTRAL"
    if price_change_pct > 0 and oi_change_pct > 0: return "LONG BUILDUP"
    if price_change_pct < 0 and oi_change_pct > 0: return "SHORT BUILDUP"
    if price_change_pct > 0 and oi_change_pct < 0: return "SHORT COVERING"
    return "LONG UNWINDING"

def wall_premium_proxy(rows, strike, side):
    """Daily OI-plus-premium pattern; never establishes actual writing direction."""
    eligible = [r for r in rows if r.get("OptnTp") == side
                and abs(num(r.get("StrkPric")) - strike) < 0.001]
    if not eligible: return {"label": "NO DATA", "oi_change": 0, "premium_pct": None}
    row = max(eligible, key=lambda r: num(r.get("OpnIntrst")))
    current = num(row.get("ClsPric"))
    previous = num(row.get("PrvsClsgPric"))
    oi_delta = num(row.get("ChngInOpnIntrst"))
    volume = num(row.get("TtlTradgVol"))
    if current <= 0 or previous <= 0 or volume <= 0:
        return {"label": "INSUFFICIENT PREMIUM DATA", "oi_change": round(oi_delta), "premium_pct": None}
    premium_change = pct(current, previous)
    label = "MIXED / NO CONFIRMATION"
    if oi_delta > 0 and premium_change < -0.5: label = "WRITING-LIKE"
    elif oi_delta < 0 and premium_change > 0.5: label = "UNWINDING/COVERING-LIKE"
    return {"label": label, "oi_change": round(oi_delta),
            "premium_pct": round(premium_change, 2)}

def chain_metrics(rows, spot):
    by_strike = defaultdict(lambda: {"CE": 0.0, "PE": 0.0, "ce_delta": 0.0, "pe_delta": 0.0})
    for row in rows:
        side = row.get("OptnTp")
        strike = num(row.get("StrkPric"))
        if side not in ("CE", "PE") or strike <= 0: continue
        oi = max(num(row.get("OpnIntrst")), 0)
        delta = num(row.get("ChngInOpnIntrst"))
        by_strike[strike][side] += oi
        by_strike[strike][side.lower() + "_delta"] += delta
    valid = [(k, v) for k, v in by_strike.items() if (v["CE"] + v["PE"]) > 0]
    ce = sum(v["CE"] for _, v in valid)
    pe = sum(v["PE"] for _, v in valid)
    pain = max_pain(rows)
    if len(valid) < 12 or ce < 1 or pe < 1 or pain is None:
        return None
    put_wall = max(valid, key=lambda kv: kv[1]["PE"])[0]
    call_wall = max(valid, key=lambda kv: kv[1]["CE"])[0]
    support_candidates = [(k, v["PE"]) for k, v in valid if k <= spot and k >= spot * 0.80 and v["PE"] > 0]
    resist_candidates = [(k, v["CE"]) for k, v in valid if k >= spot and k <= spot * 1.20 and v["CE"] > 0]
    near_put = max(support_candidates, key=lambda kv: kv[1])[0] if support_candidates else None
    near_call = max(resist_candidates, key=lambda kv: kv[1])[0] if resist_candidates else None
    previous_rows = []
    previous_oi = {}
    for strike, v in by_strike.items():
        old_ce = max(0.0, v["CE"] - v["ce_delta"])
        old_pe = max(0.0, v["PE"] - v["pe_delta"])
        previous_oi[strike] = {"CE": old_ce, "PE": old_pe}
        for side, amount in (("CE", old_ce), ("PE", old_pe)):
            previous_rows.append({"StrkPric": str(strike), "OptnTp": side, "OpnIntrst": str(amount)})
    historical_pain = max_pain(previous_rows)
    previous_put_wall = max(previous_oi, key=lambda k: previous_oi[k]["PE"]) if previous_oi else None
    previous_call_wall = max(previous_oi, key=lambda k: previous_oi[k]["CE"]) if previous_oi else None
    prev_ce = sum(v["CE"] for v in previous_oi.values())
    prev_pe = sum(v["PE"] for v in previous_oi.values())
    return {
        "strike_count": len(valid), "ce_oi": round(ce), "pe_oi": round(pe),
        "pcr": round(pe / ce, 3), "previous_pcr": round(prev_pe / prev_ce, 3) if prev_ce else None,
        "call_wall": call_wall, "put_wall": put_wall,
        "previous_call_wall": previous_call_wall, "previous_put_wall": previous_put_wall,
        "call_wall_shift": call_wall - previous_call_wall if previous_call_wall else None,
        "put_wall_premium_proxy": wall_premium_proxy(rows, put_wall, "PE"),
        "call_wall_premium_proxy": wall_premium_proxy(rows, call_wall, "CE"),
        "put_wall_shift": put_wall - previous_put_wall if previous_put_wall else None,
        "near_call_wall": near_call, "near_put_wall": near_put,
        "max_pain": pain["strike"], "previous_max_pain": historical_pain["strike"] if historical_pain else None,
        "max_pain_payout_units": pain["payout_price_units"],
        "ce_oi_change": round(sum(v["ce_delta"] for _, v in valid)),
        "pe_oi_change": round(sum(v["pe_delta"] for _, v in valid)),
    }

def ema(values, length):
    if len(values) < length: return None
    val = sum(values[:length]) / length
    alpha = 2.0 / (length + 1)
    for x in values[length:]:
        val = x * alpha + val * (1 - alpha)
    return val

def tech_metrics(rows):
    """Cash EOD 20/50 averages, RSI, MACD, crosses and 60-session Fibonacci."""
    return compute_technicals(rows)

def research_candidate(symbol, future, chain, tech, asof):
    """Price levels use NSE cash-stock reference (not executable futures fills)."""
    f_close = num(future.get("SttlmPric")) or num(future.get("ClsPric"))
    f_prior = num(future.get("PrvsClsgPric"))
    oi = num(future.get("OpnIntrst"))
    oi_delta = num(future.get("ChngInOpnIntrst"))
    oi_previous = oi - oi_delta
    f_volume = num(future.get("TtlTradgVol"))
    if min(f_close, f_prior, oi, oi_previous) <= 0 or f_volume < 100 or oi < 5000:
        return None
    fpct, opct = pct(f_close, f_prior), pct(oi, oi_previous)
    regime = classify_futures(fpct, opct)
    # A short-covering rally or long unwind is a WATCH condition, not fresh momentum.
    if regime not in ("LONG BUILDUP", "SHORT BUILDUP"): return None
    if abs(fpct) < 0.5 or abs(opct) < 2.0: return None
    direction = "LONG" if regime in ("LONG BUILDUP", "SHORT COVERING") else "SHORT"
    side = 1 if direction == "LONG" else -1
    price, atr = tech["close"], tech["atr14"]
    if atr <= 0 or price <= 0 or tech["cash_volume"] <= 0: return None
    if abs(price - num(future.get("UndrlygPric"), price)) / price > 0.025:
        return None  # wrong underlying or inconsistent settlement snapshot
    if direction == "LONG" and (price <= tech["ema20"] or price < tech["prev5_high"] * 0.995): return None
    if direction == "SHORT" and (price >= tech["ema20"] or price > tech["prev5_low"] * 1.005): return None
    technical = technical_confirmation(tech, direction)
    if not technical["approved"]: return None
    trigger_buffer = max(0.07 * atr, price * 0.0004)
    if direction == "LONG":
        entry = tech["high"] + trigger_buffer
        sl = tech["low"] - 0.12 * atr
        gap_limit = entry + 0.5 * atr
    else:
        entry = tech["low"] - trigger_buffer
        sl = tech["high"] + 0.12 * atr
        gap_limit = entry - 0.5 * atr
    risk = abs(entry - sl)
    if (not (0.55 * atr <= risk <= 3.0 * atr) or abs(entry - price) > 1.6 * atr
            or sl <= 0 or risk / entry > 0.045):
        return None
    t1 = entry + side * 2.55 * risk
    t2 = entry + side * 3.55 * risk
    if abs(t1 - entry) / entry > 0.11: return None  # 1-5 session horizon: avoid impractically distant targets
    cost = entry * 0.0015  # modelled round-trip impact, not exact client charges
    net_rr = (abs(t1-entry) - cost) / (risk + cost)
    if net_rr < 2: return None
    if direction == "LONG":
        wall = chain["near_call_wall"]
        if wall is not None and entry < wall < t1: return None
    else:
        wall = chain["near_put_wall"]
        if wall is not None and t1 < wall < entry: return None

    # Independent evidence groups: futures max40; options max35; technicals max25.
    futures_score = min(40, 26 + (8 if abs(opct)>=5 else 5) +
                        (6 if abs(fpct)>=1 else 4))
    options_score = 0
    put_wall = chain["near_put_wall"]
    call_wall = chain["near_call_wall"]
    supportive = put_wall if direction == "LONG" else call_wall
    if supportive and ((0 <= price-supportive <= price*0.075) if side>0
                       else (0 <= supportive-price <= price*0.075)):
        options_score += 8
    # Opposing OI wall must not intervene before T1 (already checked).
    options_score += 7
    delta_relative = (chain["pe_oi_change"]-chain["ce_oi_change"]) * side
    if delta_relative>0: options_score += 8
    previous_pcr = chain.get("previous_pcr")
    if previous_pcr is not None and side*(chain["pcr"]-previous_pcr)>0:
        options_score += 4
    elif (0.75<=chain["pcr"]<=1.8 if side>0 else 0.3<=chain["pcr"]<=1.15):
        options_score += 2
    wall_shift = chain.get("put_wall_shift" if side>0 else "call_wall_shift")
    if wall_shift is not None and side*wall_shift>0: options_score += 3
    proxy = chain["put_wall_premium_proxy" if side>0 else "call_wall_premium_proxy"]
    if proxy.get("label")=="WRITING-LIKE": options_score += 4
    if side*(chain["max_pain"]-price)>0: options_score += 1
    options_score = min(35,options_score)
    technical_score = technical["score"]
    score = futures_score + options_score + technical_score
    # Explicit high-confluence gates, never a daily quota.
    if (futures_score<35 or options_score<23 or technical_score<23 or score<85):
        return None
    def rnd(x): return round(x, 2)
    return {
        "signal_id": f"{asof:%Y%m%d}-{symbol}-{direction}",
        "symbol": symbol, "direction": direction, "regime": regime, "score": score,
        "futures_expiry": future["XpryDt"], "futures_settlement": rnd(f_close),
        "futures_change_pct": round(fpct, 2), "futures_oi": round(oi),
        "futures_oi_change": round(oi_delta), "futures_oi_change_pct": round(opct, 2),
        "futures_volume": round(f_volume), "cash_close": rnd(price),
        "cash_rvol20": round(tech["rvol20"], 2), "ema20": rnd(tech["ema20"]),
        "ema50":rnd(tech["ema50"]), "sma20":rnd(tech["sma20"]), "sma50":rnd(tech["sma50"]),
        "rsi14":round(tech["rsi14"],2), "macd":round(tech["macd"],4),
        "macd_signal":round(tech["macd_signal"],4),
        "macd_hist":round(tech["macd_hist"],4),
        "ema_crossover":tech["ema_crossover"],
        "sma_crossover":tech["sma_crossover"], "macd_crossover":tech.get("macd_crossover"),
        "fib_swing_high60":rnd(tech["fib_swing_high60"]),
        "fib_swing_low60":rnd(tech["fib_swing_low60"]),
        "fib_support":rnd(tech["fib_support"]) if tech["fib_support"] is not None else None,
        "fib_resistance":rnd(tech["fib_resistance"]) if tech["fib_resistance"] is not None else None,
        "fib_levels60":{k:rnd(v) for k,v in tech["fib_levels60"].items()},
        "technical_reasons":technical["reasons"],
        "futures_score":futures_score, "options_score":options_score,
        "technical_score":technical_score,
        "atr14": rnd(atr), "put_wall": chain["put_wall"], "call_wall": chain["call_wall"],
        "near_put_wall": chain["near_put_wall"], "near_call_wall": chain["near_call_wall"],
        "max_pain": chain["max_pain"], "previous_max_pain": chain["previous_max_pain"],
        "pcr": chain["pcr"], "previous_pcr": chain["previous_pcr"],
        "previous_put_wall": chain["previous_put_wall"],
        "previous_call_wall": chain["previous_call_wall"],
        "put_wall_shift": chain["put_wall_shift"], "call_wall_shift": chain["call_wall_shift"],
        "put_wall_premium_proxy": chain["put_wall_premium_proxy"],
        "call_wall_premium_proxy": chain["call_wall_premium_proxy"],
        "pe_oi_change": chain["pe_oi_change"], "ce_oi_change": chain["ce_oi_change"],
        "entry_trigger": rnd(entry), "stop_loss": rnd(sl),
        "target_1": rnd(t1), "target_2": rnd(t2),
        "modelled_net_rr_t1": round(net_rr, 2), "modelled_roundtrip_cost_pct": 0.15,
        "gap_skip_level": rnd(gap_limit), "holding_sessions": "1-5",
        "exit": "Price crosses hard stop; close beyond reversed daily structure or adverse futures OI regime at next EOD; time exit after five sessions.",
        "underlying": "NSE cash equity reference; futures contract has a separate price/basis.",
    }
