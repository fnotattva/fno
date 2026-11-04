"""Independent, optional EOD discretionary research watchlist; no forced calls.

A candidate can fail every strict A-tier scanner gate. It must nevertheless have
verified NSE EOD cash/futures data, liquidity, an observable market structure
pattern, a next-session *conditional* trigger and a clear invalidation. It is
NEVER labeled a validated trade or shown as an executed order.
"""
from __future__ import annotations
from math import isfinite

def safe_num(value):
    try:
        out = float(str(value or "").replace(",", ""))
        return out if isfinite(out) else 0.0
    except (TypeError, ValueError):
        return 0.0

def change_pct(current, previous):
    return 100*(current/previous-1) if previous>0 else 0.0

def _regime(future):
    f = safe_num(future.get("SttlmPric")) or safe_num(future.get("ClsPric"))
    prior = safe_num(future.get("PrvsClsgPric"))
    oi = safe_num(future.get("OpnIntrst"))
    old_oi = oi-safe_num(future.get("ChngInOpnIntrst"))
    if min(f,prior,oi,old_oi)<=0:return ("UNVERIFIED",0.0,0.0)
    fpct=change_pct(f,prior); opct=change_pct(oi,old_oi)
    if fpct>0.05 and opct>0.5: regime="LONG BUILDUP"
    elif fpct< -0.05 and opct>0.5:regime="SHORT BUILDUP"
    elif fpct>0.05 and opct< -0.5:regime="SHORT COVERING"
    elif fpct< -0.05 and opct< -0.5:regime="LONG UNWINDING"
    else: regime="MIXED / NEUTRAL"
    return regime,fpct,opct

def expert_watch_candidate(symbol,future,chain,tech,asof):
    """Return one auditable non-A-tier WATCH idea, else None.

    This function deliberately does *not* require aligned EMA/SMA, MACD, RSI,
    a strong options chain, high conviction score or a 2R technical target.
    Missing independent evidence is disclosed, not silently scored as present.
    """
    price=safe_num(tech.get("close"))
    hi=safe_num(tech.get("high")); low=safe_num(tech.get("low"))
    op=safe_num(tech.get("open")); atr=safe_num(tech.get("atr14"))
    vol=safe_num(tech.get("cash_volume")); rvol=safe_num(tech.get("rvol20"))
    fvol=safe_num(future.get("TtlTradgVol"))
    foi=safe_num(future.get("OpnIntrst"))
    if min(price,hi,low,op,atr,vol,foi)<=0 or hi<=low or fvol<100 or foi<5000:
        return None
    # Absolute notional turnover floor; avoid illiquid penny-stock 'breakouts'.
    if price*vol<150_000_000 or rvol<1.0:return None
    regime,fpct,opct=_regime(future)
    if regime=="UNVERIFIED":return None
    prior_high=safe_num(tech.get("prev20_high"))
    prior_low=safe_num(tech.get("prev20_low"))
    high5=safe_num(tech.get("prev5_high"));low5=safe_num(tech.get("prev5_low"))
    rsi=safe_num(tech.get("rsi14"))
    if min(prior_high,prior_low,high5,low5)<=0 or prior_high<=prior_low:return None
    frac=(price-low)/(hi-low)
    upbar=price>op and frac>=0.65
    downbar=price<op and frac<=0.35
    patterns=[]
    # Cash-market price and participation can lead slow MAs and futures OI.
    if (price>prior_high and upbar and rvol>=1.4 and
        price<=prior_high+1.5*atr and rsi<82):
        patterns.append((4,"20-session cash breakout with participation","LONG"))
    if (price<prior_low and downbar and rvol>=1.4 and
        price>=prior_low-1.5*atr and rsi>18):
        patterns.append((4,"20-session cash breakdown with participation","SHORT"))
    # Leading futures positioning near a price-level decision, even when
    # trend oscillators or CE/PE positioning have not yet aligned.
    if regime=="LONG BUILDUP" and fpct>=0.45 and opct>=2.5 and upbar and rvol>=1.10 and price>=high5-0.5*atr:
        patterns.append((3,"Futures OI expansion near five-day upside decision","LONG"))
    if regime=="SHORT BUILDUP" and fpct<=-0.45 and opct>=2.5 and downbar and rvol>=1.10 and price<=low5+0.5*atr:
        patterns.append((3,"Futures OI expansion near five-day downside decision","SHORT"))
    # A wall-adjacent cash rejection may precede indicator confirmation.
    pewall=chain.get("near_put_wall") if chain else None
    cewall=chain.get("near_call_wall") if chain else None
    if (pewall and 0<=price-pewall<=0.035*price and
        25<=rsi<=50 and upbar and rvol>=1.25 and low<=pewall*1.015):
        patterns.append((2,"Potential put-wall rejection/reversal, unconfirmed","LONG"))
    if (cewall and 0<=cewall-price<=0.035*price and
        50<=rsi<=75 and downbar and rvol>=1.25 and hi>=cewall*0.985):
        patterns.append((2,"Potential call-wall rejection/reversal, unconfirmed","SHORT"))
    if not patterns:return None
    patterns.sort(reverse=True)
    rank,reason,direction=patterns[0]
    side=1 if direction=="LONG" else -1
    # Only informational next-day price-level decision, NOT an A-tier entry.
    trigger=hi+max(0.05*atr, price*0.0004) if side>0 else low-max(0.05*atr,price*0.0004)
    invalidation=low-0.10*atr if side>0 else hi+0.10*atr
    prospective_risk=abs(trigger-invalidation)
    # A watch idea may have no tradable risk plan, which must be stated.
    manageable=prospective_risk/trigger<=0.045
    near_opposing=cewall if side>0 else pewall
    obstacle=bool(near_opposing and
                  ((trigger<near_opposing<trigger+2.0*prospective_risk) if side>0
                  else (trigger-2.0*prospective_risk<near_opposing<trigger)))
    issues=[]
    if not chain: issues.append("Full same-expiry options OI context unavailable")
    else:
        issues.append("Option walls are positioning context, not guaranteed price barriers")
        if obstacle: issues.append("Opposing options OI wall may obstruct a 2R target")
    if regime not in ("LONG BUILDUP","SHORT BUILDUP"):issues.append("Futures regime not a fresh directional buildup")
    elif (regime=="LONG BUILDUP")!=(side>0): issues.append("Futures buildup disagrees with price setup")
    ema20=safe_num(tech.get("ema20"));ema50=safe_num(tech.get("ema50"))
    sma20=safe_num(tech.get("sma20"));sma50=safe_num(tech.get("sma50"))
    trend=ema20>ema50 and sma20>sma50 if side>0 else ema20<ema50 and sma20<sma50
    if not trend:issues.append("20/50 EMA/SMA trend does not confirm")
    macd=safe_num(tech.get("macd_hist"))
    if side*macd<=0:issues.append("MACD histogram not supportive")
    if side>0 and not 52<=rsi<=70 or side<0 and not 30<=rsi<=48:
        issues.append(f"RSI14 {rsi:.1f} outside strict momentum band")
    if not manageable:issues.append("Indicative watch invalidation exceeds 4.5% risk")
    if not issues:issues.append("Not fully evaluated against all strict option and risk gates")
    quote=lambda x:round(x,2)
    return {
        "id":f"{asof:%Y%m%d}-{symbol}-{direction}-EXPERT",
        "symbol":symbol, "directional_bias":direction, "status":"EXPERT WATCH — NOT AN A-TIER TRADE",
        "pattern":reason, "pattern_priority":rank, "market_date":asof.isoformat(),
        "cash_close":quote(price), "cash_volume":round(vol), "cash_turnover_inr":round(price*vol),
        "relative_volume":round(rvol,2), "futures_regime":regime,
        "futures_change_pct":round(fpct,2), "futures_oi_change_pct":round(opct,2),
        "futures_volume":round(fvol), "rsi14":round(rsi,1),
        "ema20":quote(ema20), "ema50":quote(ema50),
        "macd_hist":round(macd,4),
        "put_wall":chain.get("near_put_wall") if chain else None,
        "call_wall":chain.get("near_call_wall") if chain else None,
        "max_pain":chain.get("max_pain") if chain else None,
        "price_decision_level":quote(trigger),
        "indicative_invalidation":quote(invalidation) if manageable else None,
        "trigger_condition":("Monitor next session for a verified price and volume breakout beyond the decision level. "
                             "Do not enter automatically. Recheck gap, slippage, OI walls and post-open structure."),
        "data_quality":"Verified NSE EOD cash and futures, options " +
            ("present" if chain else "incomplete/unavailable"),
        "caveats":issues,
        "not_a_call":True, "recommendation":None,
    }
