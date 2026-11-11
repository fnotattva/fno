"""Daily FnO Tattva actionable research shortlist allocation.

Exactly zero to three *new* A/B/C conditional entry ideas across categories.
Prior open research reviews count against a conservative active-idea capacity,
but DO NOT imply an executed account position.
"""

MAX_DAILY_FRESH = 3
IDEAL_FRESH = 2
MAX_CONCURRENT_RESEARCH_IDEAS = 3


def choose_daily_shortlist(a_tier, b_tier, c_tier, active_research=None):
    """Choose the best two by default and an exceptional third when warranted.

    No selection is manufactured if insufficient signals qualify. A is always
    ranked above B above C, never relabelled. Existing tracked research ideas
    occupy conservative capacity but aren't claimed to be actual open trades.
    Returns retained lists (A, B, C) and an auditable selection summary.
    """
    active_research = active_research or []
    active_symbols = {
        r.get("signal", {}).get("symbol") for r in active_research
        if isinstance(r, dict) and isinstance(r.get("signal"), dict)
    }
    active_symbols.discard(None)
    slots = max(0, min(MAX_DAILY_FRESH, MAX_CONCURRENT_RESEARCH_IDEAS-len(active_symbols)))
    pools = (
        ("A", list(a_tier or [])),
        ("B", list(b_tier or [])),
        ("C", list(c_tier or [])),
    )
    filtered = []
    seen = set(active_symbols)
    for tier, candidates in pools:
        for signal in candidates:
            symbol = signal.get("symbol")
            if not symbol or symbol in seen:
                continue
            # Input arrays are pre-sorted within their tier by existing
            # evidence scores. Cross-tier priority is A > B > C.
            filtered.append((tier, signal))
            seen.add(symbol)

    chosen = filtered[:min(IDEAL_FRESH,slots)]
    third = filtered[len(chosen):len(chosen)+1]
    if len(chosen)==IDEAL_FRESH and slots>=3 and third:
        tier, plan = third[0]
        # The third should be exceptional; no C-tier third just to reach 3.
        if tier=="A" or (
            tier=="B"
            and float(plan.get("modelled_net_rr_t1",0) or 0)>=1.5
            and float(plan.get("cash_rvol20",0) or 0)>=1.5
            and plan.get("futures_regime") in ("LONG BUILDUP","SHORT BUILDUP")
            and abs(float(plan.get("futures_oi_change_pct",0) or 0))>=2.0
        ):
            chosen.append((tier,plan))

    picked={"A":[],"B":[],"C":[]}
    for tier,signal in chosen:
        picked[tier].append(signal)
    return picked["A"],picked["B"],picked["C"],{
        "daily_fresh_cap": MAX_DAILY_FRESH,
        "normal_fresh_goal": IDEAL_FRESH,
        "concurrent_research_cap":MAX_CONCURRENT_RESEARCH_IDEAS,
        "prior_research_ideas_under_review":len(active_symbols),
        "fresh_research_slots":slots,
        "fresh_conditional_ideas":len(chosen),
        "qualified_pre_shortlist":len(filtered),
        "not_selected":max(0,len(filtered)-len(chosen)),
        "note":("Tracked ideas count conservatively against capacity but may not "
                "be real filled holdings; broker positions are unknown. An "
                "exceptional third needs A-tier quality or B-tier momentum "
                "and >=1.5R modelled net T1. Zero ideas is valid.")
    }
