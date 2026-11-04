"""Pure NSE futures/options EOD research calculations; no broker and no orders."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite

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
    return {
        "strike_count": len(valid), "ce_oi": round(ce), "pe_oi": round(pe),
        "pcr": round(pe / ce, 3), "call_wall": call_wall, "put_wall": put_wall,
        "near_call_wall": near_call, "near_put_wall": near_put,
        "max_pain": pain["strike"], "max_pain_payout_units": pain["payout_price_units"],
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
    """rows: valid chronological CM OHLCV, including most recent date."""
    if len(rows) < 22: return None
    closes = [num(r.get("ClsPric")) for r in rows]
    highs = [num(r.get("HghPric")) for r in rows]
    lows = [num(r.get("LwPric")) for r in rows]
    volumes = [num(r.get("TtlTradgVol")) for r in rows]
    if min(closes) <= 0 or min(highs) <= 0 or min(lows) <= 0:
        return None
    true_ranges = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]),
                       abs(lows[i] - closes[i-1])) for i in range(1, len(rows))]
    atr14 = sum(true_ranges[-14:]) / 14
    vol20 = sum(volumes[-21:-1]) / 20
    return {
        "close": closes[-1], "high": highs[-1], "low": lows[-1],
        "open": num(rows[-1].get("OpnPric")), "ema20": ema(closes, 20),
        "ema50": ema(closes, 50), "atr14": atr14,
        "rvol20": volumes[-1] / vol20 if vol20 > 0 else 0,
        "prev5_high": max(highs[-6:-1]), "prev5_low": min(lows[-6:-1]),
        "prev20_high": max(highs[-21:-1]), "prev20_low": min(lows[-21:-1]),
        "cash_volume": volumes[-1], "sessions": len(rows),
    }

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
    if regime == "NEUTRAL": return None
    direction = "LONG" if regime in ("LONG BUILDUP", "SHORT COVERING") else "SHORT"
    side = 1 if direction == "LONG" else -1
    price, atr = tech["close"], tech["atr14"]
    if atr <= 0 or price <= 0 or tech["cash_volume"] <= 0: return None
    if abs(price - num(future.get("UndrlygPric"), price)) / price > 0.025:
        return None  # wrong underlying or inconsistent settlement snapshot
    if direction == "LONG" and (price <= tech["ema20"] or price < tech["prev5_high"] * 0.995): return None
    if direction == "SHORT" and (price >= tech["ema20"] or price > tech["prev5_low"] * 1.005): return None
    if tech["rvol20"] < 0.75: return None
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
    if abs(t1 - entry) / entry > 0.11: return None  # 1-5 session horizon: avoid impractically distant targets\n    cost = entry * 0.0015  # modelled round-trip impact, not exact client charges
    net_rr = (abs(t1-entry) - cost) / (risk + cost)
    if net_rr < 2: return None
    if direction == "LONG":
        wall = chain["near_call_wall"]
        if wall is not None and entry < wall < t1: return None
    else:
        wall = chain["near_put_wall"]
        if wall is not None and t1 < wall < entry: return None

    futures_score = 26 if regime in ("LONG BUILDUP", "SHORT BUILDUP") else 8
    futures_score += 8 if abs(opct) >= 5 else 5 if abs(opct) >= 2 else 2
    futures_score += 6 if abs(fpct) >= 1 else 4 if abs(fpct) >= 0.5 else 1
    futures_score = min(futures_score, 40)
    options_score = 0
    supportive = chain["near_put_wall"] if direction == "LONG" else chain["near_call_wall"]
    if supportive and abs(price-supportive)/price <= 0.10: options_score += 10
    opposing = chain["near_call_wall"] if direction == "LONG" else chain["near_put_wall"]\n    options_score += 9 if opposing is not None else 3
    if direction == "LONG":
        if chain["pe_oi_change"] > chain["ce_oi_change"]: options_score += 7
        if 0.75 <= chain["pcr"] <= 1.9: options_score += 5
        if chain["max_pain"] >= price: options_score += 4
    else:
        if chain["ce_oi_change"] > chain["pe_oi_change"]: options_score += 7
        if 0.3 <= chain["pcr"] <= 1.25: options_score += 5
        if chain["max_pain"] <= price: options_score += 4
    options_score = min(options_score, 35)
    technical_score = 7 + 8  # EMA20 trend + prior-five-day extreme proximity
    if tech["rvol20"] >= 1.25: technical_score += 6
    if side * (price - tech["open"]) > 0: technical_score += 4
    score = futures_score + options_score + technical_score
    if score < 63: return None
    def rnd(x): return round(x, 2)
    return {
        "signal_id": f"{asof:%Y%m%d}-{symbol}-{direction}",
        "symbol": symbol, "direction": direction, "regime": regime, "score": score,
        "futures_expiry": future["XpryDt"], "futures_settlement": rnd(f_close),
        "futures_change_pct": round(fpct, 2), "futures_oi": round(oi),
        "futures_oi_change": round(oi_delta), "futures_oi_change_pct": round(opct, 2),
        "futures_volume": round(f_volume), "cash_close": rnd(price),
        "cash_rvol20": round(tech["rvol20"], 2), "ema20": rnd(tech["ema20"]),
        "atr14": rnd(atr), "put_wall": chain["put_wall"], "call_wall": chain["call_wall"],
        "near_put_wall": chain["near_put_wall"], "near_call_wall": chain["near_call_wall"],
        "max_pain": chain["max_pain"], "pcr": chain["pcr"],
        "pe_oi_change": chain["pe_oi_change"], "ce_oi_change": chain["ce_oi_change"],
        "entry_trigger": rnd(entry), "stop_loss": rnd(sl),
        "target_1": rnd(t1), "target_2": rnd(t2),
        "modelled_net_rr_t1": round(net_rr, 2), "modelled_roundtrip_cost_pct": 0.15,
        "gap_skip_level": rnd(gap_limit), "holding_sessions": "1-5",
        "exit": "Price crosses hard stop; close beyond reversed daily structure or adverse futures OI regime at next EOD; time exit after five sessions.",
        "underlying": "NSE cash equity reference; futures contract has a separate price/basis.",
    }
