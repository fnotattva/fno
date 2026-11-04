"""NSE cash EOD technical confluence, computed from completed OHLCV sessions only.

Indicators are descriptive and correlated; none alone demonstrates predictive accuracy.
All levels are cash-market references, NOT executable stock-futures prices.
"""
from __future__ import annotations
from math import isfinite

MIN_SESSIONS = 65

def _num(value):
    try:
        number = float(str(value or "").replace(",", ""))
        return number if isfinite(number) else 0.0
    except (ValueError, TypeError):
        return 0.0

def sma_series(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    rolling = sum(values[:period])
    out[period - 1] = rolling / period
    for i in range(period, len(values)):
        rolling += values[i] - values[i - period]
        out[i] = rolling / period
    return out

def ema_series(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    avg = sum(values[:period]) / period
    out[period - 1] = avg
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        avg = values[i] * alpha + avg * (1 - alpha)
        out[i] = avg
    return out

def wilder_rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    changes = [values[i] - values[i-1] for i in range(1, period + 1)]
    up = sum(max(delta, 0) for delta in changes) / period
    down = sum(max(-delta, 0) for delta in changes) / period
    def compute(u, d):
        if u == 0 and d == 0: return 50.0
        if d == 0: return 100.0
        return 100 - 100 / (1 + u / d)
    out[period] = compute(up, down)
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i-1]
        up = (up * (period-1) + max(diff, 0)) / period
        down = (down * (period-1) + max(-diff, 0)) / period
        out[i] = compute(up, down)
    return out

def macd_series(values):
    fast, slow = ema_series(values, 12), ema_series(values, 26)
    macd = [None if a is None or b is None else a-b for a,b in zip(fast,slow)]
    valid = [x for x in macd if x is not None]
    signal_valid = ema_series(valid, 9)
    signal = [None] * (len(macd) - len(valid)) + signal_valid
    hist = [None if a is None or b is None else a-b for a,b in zip(macd,signal)]
    return macd, signal, hist

def _recent_cross(fast, slow, lookback=5):
    for i in range(len(fast)-1, max(1, len(fast)-lookback-1), -1):
        a0, b0, a1, b1 = fast[i-1],slow[i-1],fast[i],slow[i]
        if None in (a0,b0,a1,b1): continue
        if a0 <= b0 and a1 > b1:
            return {"direction": "BULLISH", "sessions_ago": len(fast)-1-i}
        if a0 >= b0 and a1 < b1:
            return {"direction": "BEARISH", "sessions_ago": len(fast)-1-i}
    return None

def compute_technicals(rows):
    """Chronologically ordered *complete* CM candles, latest session included."""
    if len(rows) < MIN_SESSIONS:
        return None
    opens=[_num(r.get("OpnPric")) for r in rows]
    highs=[_num(r.get("HghPric")) for r in rows]
    lows=[_num(r.get("LwPric")) for r in rows]
    closes=[_num(r.get("ClsPric")) for r in rows]
    volumes=[_num(r.get("TtlTradgVol")) for r in rows]
    for o,h,l,c,v in zip(opens,highs,lows,closes,volumes):
        if min(o,h,l,c,v)<=0 or not l<=min(o,c)<=max(o,c)<=h:
            return None
    e20,e50=ema_series(closes,20),ema_series(closes,50)
    s20,s50=sma_series(closes,20),sma_series(closes,50)
    rsi=wilder_rsi(closes,14)
    macd,signal,hist=macd_series(closes)
    if any(series[-1] is None for series in (e20,e50,s20,s50,rsi,macd,signal,hist)):
        return None
    ranges=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),
                abs(lows[i]-closes[i-1])) for i in range(1,len(rows))]
    atr14=sum(ranges[-14:])/14
    avg_vol=sum(volumes[-21:-1])/20
    if min(atr14, avg_vol)<=0: return None
    previous_hi=max(highs[-61:-1])
    previous_lo=min(lows[-61:-1])
    width=previous_hi-previous_lo
    if width<=0: return None
    fib={str(ratio): previous_lo + width*ratio for ratio in (0,0.236,0.382,0.5,0.618,0.786,1)}
    below=[v for v in fib.values() if v < closes[-1]]
    above=[v for v in fib.values() if v > closes[-1]]
    cross_ema=_recent_cross(e20,e50)
    cross_sma=_recent_cross(s20,s50)
    cross_macd=_recent_cross(macd,signal)
    return {
        "sessions": len(rows), "open":opens[-1], "high":highs[-1], "low":lows[-1],
        "close":closes[-1], "cash_volume":volumes[-1],
        "rvol20":volumes[-1]/avg_vol, "atr14":atr14,
        "ema20":e20[-1], "ema50":e50[-1], "sma20":s20[-1], "sma50":s50[-1],
        "ema20_prev":e20[-2], "ema50_prev":e50[-2],
        "rsi14":rsi[-1], "rsi14_prev":rsi[-2],
        "macd":macd[-1], "macd_signal":signal[-1],
        "macd_hist":hist[-1], "macd_hist_prev":hist[-2],
        "ema_crossover":cross_ema, "sma_crossover":cross_sma, "macd_crossover":cross_macd,
        "prev5_high":max(highs[-6:-1]), "prev5_low":min(lows[-6:-1]),
        "prev20_high":max(highs[-21:-1]), "prev20_low":min(lows[-21:-1]),
        "fib_swing_high60":previous_hi, "fib_swing_low60":previous_lo,
        "fib_levels60":fib,
        "fib_support":max(below) if below else None,
        "fib_resistance":min(above) if above else None,
    }

def technical_confirmation(tech, direction):
    """Independent mandatory trend, momentum and participation gates.
    Returns reasons and a 0-25 evidence score, NOT a calibrated win probability.
    """
    sign=1 if direction=="LONG" else -1
    price=tech["close"]
    rsi=tech["rsi14"]
    macd_gap=tech["macd"]-tech["macd_signal"]
    hist=tech["macd_hist"]
    trend=all([
        sign*(price-tech["ema20"])>0,
        sign*(price-tech["sma20"])>0,
        sign*(tech["ema20"]-tech["ema50"])>0,
        sign*(tech["sma20"]-tech["sma50"])>0,
        sign*(tech["ema20"]-tech["ema20_prev"])>0,
    ])
    rsi_valid=52 <= rsi <= 70 if sign>0 else 30 <= rsi <= 48
    macd_valid=sign*macd_gap>0 and sign*hist>0
    volume_valid=tech["rvol20"]>=1.20
    if not (trend and rsi_valid and macd_valid and volume_valid):
        reasons=[]
        if not trend: reasons.append("EMA/SMA 20/50 trend not aligned")
        if not rsi_valid: reasons.append("RSI outside momentum/non-exhaustion range")
        if not macd_valid: reasons.append("MACD signal/histogram not aligned")
        if not volume_valid: reasons.append("Insufficient relative volume")
        return {"approved":False, "score":0, "reasons":reasons}
    score=9+8+4
    reasons=["EMA/SMA 20/50 aligned with rising/falling EMA20",
             f"RSI14 {rsi:.1f} and MACD histogram {hist:+.3f} confirm direction",
             f"Relative cash volume {tech['rvol20']:.2f}x"]
    if tech["rvol20"]>=1.5: score+=1
    cross=tech["ema_crossover"]
    if cross and cross["direction"]==("BULLISH" if sign>0 else "BEARISH"):
        score+=2
        reasons.append(f"EMA20/50 crossover {cross['sessions_ago']} sessions ago")
    recent_break=(price > tech["prev5_high"]) if sign>0 else (price<tech["prev5_low"])
    if recent_break:
        score+=2
        reasons.append("Close confirmed beyond preceding five-session extreme")
    return {"approved":True,"score":min(25,score),"reasons":reasons}
