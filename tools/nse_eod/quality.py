"""Evidence-calibrated quality gate for B/C conditional research plans.

Derived from a no-lookahead replay of this engine on official NSE UDiFF
archives (Mar 2025 - Nov 2026, ~1,250 A/B/C plans; parameters chosen on 2025
only and checked on held-out 2026 data). See docs/nse-eod-backtest-findings.md.

Findings that held in BOTH periods:
  * Plans with cash RVOL20 below 2.0x had negative modelled expectancy.
  * Plans in already-mature trends (EMA20-EMA50 gap > 1.2 ATR in the trade
    direction) underperformed early-trend plans.
  * Structural T1s beyond ~1.2R were reached too rarely; capping T1 at 1.2R
    improved expectancy (implemented in trade_plans.expert_trade_plan).
  * C-tier breakout/breakdown entries lost in both periods, while C-tier
    pullback/retest entries were the best performers; C breakouts are
    therefore demoted to WATCH ONLY (B-tier breakouts are unaffected).
  * Plans formed in the final 3 days before stock-futures expiry (analysed on
    the next contract with same-day all-expiry OI) showed no edge; they are
    reported as WATCH ONLY so roll days are covered but not traded.
  * Signals chasing a strongly one-sided market (F&O breadth far above/below
    50% in the trade direction) did worse; disclosed as a caution only.

These are historical observations with modest sample sizes, NOT guarantees
or calibrated win probabilities. Re-validate periodically with the replay tool.
A-tier strict logic is intentionally untouched; A plans receive the same
disclosures but are not filtered here.
"""
from __future__ import annotations

from math import isfinite

MIN_RVOL = 2.0
MAX_TREND_MATURITY_ATR = 1.2
T1_CAP_R = 1.2
MARKET_CHASE_BREADTH_GAP = 0.20


def _f(value):
    try:
        out = float(value)
        return out if isfinite(out) else None
    except (TypeError, ValueError):
        return None


def trend_maturity_atr(tech, direction):
    """Signed EMA20-EMA50 distance in ATR units, positive = with the trade."""
    ema20, ema50, atr = (_f((tech or {}).get(k)) for k in ("ema20", "ema50", "atr14"))
    if not ema20 or not ema50 or not atr or atr <= 0:
        return None
    side = 1 if direction == "LONG" else -1
    return side * (ema20 - ema50) / atr


def market_breadth(snapshots):
    """Share of fully covered F&O stocks closing above their EMA20."""
    techs = [s.get("tech") for s in (snapshots or {}).values() if s.get("tech")]
    valid = [t for t in techs if _f(t.get("close")) and _f(t.get("ema20"))]
    if len(valid) < 20:
        return None
    return sum(t["close"] > t["ema20"] for t in valid) / len(valid)


def market_context(direction, breadth):
    if breadth is None:
        return {"fno_breadth_above_ema20": None, "market_chase_caution": None}
    side = 1 if direction == "LONG" else -1
    chase = side * (breadth - 0.5) > MARKET_CHASE_BREADTH_GAP
    return {
        "fno_breadth_above_ema20": round(breadth, 3),
        "market_chase_caution": (
            "Signal is in the direction of a strongly one-sided F&O market; "
            "historically such late-move breakouts followed through less often" if chase else None),
    }


def quality_gate(plan, tech, roll_window=False):
    """Return (passes, reasons). Never modifies levels; only accepts/demotes."""
    reasons = []
    if roll_window:
        reasons.append("Expiry roll window: next-contract signals showed no edge in the replay; "
                       "research context only")
    rvol = _f(plan.get("cash_rvol20"))
    if rvol is None:
        rvol = _f((tech or {}).get("rvol20"))
    if rvol is None or rvol < MIN_RVOL:
        reasons.append(f"Cash RVOL20 {rvol if rvol is not None else 'n/a'}x below calibrated {MIN_RVOL:.1f}x minimum")
    if (str(plan.get("tier", "")).startswith("C")
            and "pullback" not in str(plan.get("entry_pattern", "")).lower()):
        reasons.append("C-tier breakout/breakdown entry (historically negative); "
                       "only C pullback/retest entries are issued")
    maturity = trend_maturity_atr(tech, plan.get("direction"))
    if maturity is None:
        reasons.append("Trend maturity (EMA20-EMA50 in ATR) unavailable")
    elif maturity >= MAX_TREND_MATURITY_ATR:
        reasons.append(f"Mature trend: EMA20-EMA50 gap {maturity:.2f} ATR >= {MAX_TREND_MATURITY_ATR} ATR")
    return (not reasons), reasons


def demote_to_watch(plan, reasons):
    """Convert a B/C plan that fails the quality gate into a WATCH-ONLY idea."""
    return {
        "id": plan["signal_id"] + "-QUALITY-DEMOTED",
        "symbol": plan["symbol"], "directional_bias": plan["direction"],
        "status": "QUALITY GATE — WATCH ONLY, NOT A TRADE PLAN",
        "pattern": plan.get("pattern", ""), "pattern_priority": plan.get("pattern_priority", 0),
        "market_date": plan.get("market_date"),
        "cash_close": plan["cash_close"], "relative_volume": plan.get("cash_rvol20") or 0.0,
        "cash_turnover_inr": 0,
        "futures_regime": plan.get("futures_regime"),
        "futures_change_pct": plan.get("futures_change_pct") or 0.0,
        "futures_oi_change_pct": plan.get("futures_oi_change_pct") or 0.0,
        "ema20": plan.get("ema20") or 0.0, "ema50": plan.get("ema50") or 0.0,
        "rsi14": plan.get("rsi14") or 0.0, "macd_hist": plan.get("macd_hist") or 0.0,
        "put_wall": plan.get("put_wall"), "call_wall": plan.get("call_wall"),
        "max_pain": plan.get("max_pain"),
        "price_decision_level": plan["entry_trigger"],
        "indicative_invalidation": plan["stop_loss"],
        "caveats": ["Demoted by evidence-calibrated quality gate: " + "; ".join(reasons)]
                   + list(plan.get("unresolved_evidence") or []),
        "quality_gate_reasons": reasons,
        "not_a_call": True, "recommendation": None,
    }


# --- Context signals from the 2025-26 cross-sectional study (24 Nov 2026) ---
# Futures premium over spot: highest-premium fifth beat the lowest by ~0.33% over
# 5 sessions in BOTH years; engine plans whose premium rank opposed the trade did
# worse in both engine versions. Delivery % above its own 20-session average
# mildly predicted outperformance. Both are CONTEXT/CAUTION, never entry/exit
# triggers. Single-day OI regimes showed no predictive value.
PREMIUM_AGAINST_RANK = 0.40
PREMIUM_DISTORTION_ABS = 0.03


def futures_premium_ranks(snapshots):
    """{symbol: (premium, rank)} from analysed futures settlement vs underlying."""
    raw = {}
    for sym, snap in (snapshots or {}).items():
        fut = (snap or {}).get("future") or {}
        settle, under = _f(fut.get("SttlmPric")) or _f(fut.get("ClsPric")), _f(fut.get("UndrlygPric"))
        if settle and under and under > 0:
            raw[sym] = settle / under - 1
    normal = sorted(v for v in raw.values() if abs(v) <= PREMIUM_DISTORTION_ABS)
    out = {}
    for sym, prem in raw.items():
        if abs(prem) > PREMIUM_DISTORTION_ABS or len(normal) < 20:
            out[sym] = (prem, None)
            continue
        below = sum(1 for v in normal if v < prem)
        out[sym] = (prem, below / (len(normal) - 1) if len(normal) > 1 else None)
    return out


def premium_context(direction, premium, rank):
    if premium is None:
        return {"futures_premium_pct": None, "futures_premium_rank": None, "futures_premium_caution": None}
    note = None
    if rank is None:
        note = ("Futures premium/discount unusually large; often a dividend, buyback or other corporate "
                "event. Check the corporate-action calendar before acting")
    else:
        against = rank < PREMIUM_AGAINST_RANK if direction == "LONG" else rank > 1 - PREMIUM_AGAINST_RANK
        if against:
            note = ("Futures premium ranks against the trade direction; in the NSE replay such plans "
                    "did worse (also check for an upcoming ex-dividend date)")
    return {"futures_premium_pct": round(100 * premium, 3),
            "futures_premium_rank": round(rank, 2) if rank is not None else None,
            "futures_premium_caution": note}


def delivery_context(symbol, today, history):
    """Delivery % today and relative to its own prior-20-session average (context only)."""
    pct = (today or {}).get(symbol)
    past = [day[symbol] for day in (history or []) if symbol in day][-20:]
    rel = pct / (sum(past) / len(past)) if pct is not None and len(past) >= 10 and sum(past) > 0 else None
    return {"delivery_pct": pct, "delivery_rel20": round(rel, 2) if rel is not None else None}
