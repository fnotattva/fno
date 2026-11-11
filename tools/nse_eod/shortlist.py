"""FnO Tattva EOD new-research shortlist: quality threshold, not a hard quota.

Normally publish two, sometimes three. Include every independently exceptional
additional A/B/C research plan; never suppress a qualifying exceptional idea
merely because three have already been shown. No candidate is forced.
Tracked research ideas and broker holdings are different concepts.
"""
from math import isfinite

NORMAL_FRESH_GOAL = 2


def _numeric(value):
    try:
        out = float(value)
        return out if isfinite(out) else 0.0
    except (TypeError, ValueError):
        return 0.0


def exceptional_additional_plan(tier, signal):
    """Independent elevated evidence gate for idea #3, #4, #5, etc.

    A already passed every strict high-conviction rule. B and C are held to
    higher-than-usual R/volume/futures confluence, not merely normal eligibility.
    A positive return or high win rate is NOT implied by crossing this rule.
    """
    if tier == "A":
        return True
    regime = signal.get("futures_regime")
    aligned = regime in ("LONG BUILDUP", "SHORT BUILDUP")
    oi = _numeric(signal.get("futures_oi_change_pct"))
    rvol = _numeric(signal.get("cash_rvol20"))
    rr = _numeric(signal.get("modelled_net_rr_t1"))
    if tier == "B":
        return aligned and oi >= 2.0 and rvol >= 1.5 and rr >= 1.5
    if tier == "C":
        return (aligned and oi >= 3.0 and rvol >= 2.0 and rr >= 2.0
                and _numeric(signal.get("pattern_priority")) >= 4)
    return False


def choose_daily_shortlist(a_tier, b_tier, c_tier, active_research=None,
                           verified_open_positions=None):
    """Two normal new ideas plus ALL extra exceptional qualified setups.

    Existing plans remain in their own daily review section; they do not
    reduce availability of new research. If actual broker positions are known,
    disclose count/exposure to the user, but do not silently discard other
    exceptional research. The user decides whether to open a trade.
    """
    active_research = active_research or []
    under_review = {
        r.get("signal", {}).get("symbol") for r in active_research
        if isinstance(r, dict) and isinstance(r.get("signal"), dict)
    }
    under_review.discard(None)
    actual_holdings = set(verified_open_positions or [])
    seen = set(under_review)
    ranked = []
    for tier, candidates in (("A", a_tier or []),
                             ("B", b_tier or []),
                             ("C", c_tier or [])):
        for signal in candidates:
            symbol = signal.get("symbol")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            # Tier priority A > B > C; input sorted by genuine quality within.
            ranked.append((tier, signal))

    chosen = ranked[:NORMAL_FRESH_GOAL]
    additional = [(tier, signal) for tier, signal in ranked[NORMAL_FRESH_GOAL:]
                  if exceptional_additional_plan(tier, signal)]
    chosen.extend(additional)

    selected = {"A":[], "B":[], "C":[]}
    for tier, signal in chosen:
        selected[tier].append(signal)

    return selected["A"], selected["B"], selected["C"], {
        "normal_fresh_goal": NORMAL_FRESH_GOAL,
        "hard_daily_cap": None,
        "unlimited_exceptional_setups": True,
        "exceptional_ideas_beyond_normal": len(additional),
        "prior_research_ideas_under_review":len(under_review),
        "verified_open_positions_count":len(actual_holdings),
        "fresh_conditional_ideas":len(chosen),
        "qualified_pre_shortlist":len(ranked),
        "not_selected":len(ranked)-len(chosen),
        "no_forced_trades":True,
        "selection_rule":"Two normal highest-ranked by tier/evidence, plus all additional exceptional A/B/C setups that pass elevated per-tier gates",
        "note":("Open or pending research reviews DO NOT cap new research ideas. "
                "Unknown broker holdings are not assumed. Present portfolio "
                "correlation, sector concentration, costs, leverage and aggregate "
                "risk concerns if several setups appear. More than three is "
                "allowed ONLY on exceptional evidence, not as a daily quota."),
    }
