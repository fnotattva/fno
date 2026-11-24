"""Summarise replay outcomes. python3 analyze.py FILE.jsonl [--features]"""
import json, random, sys
from statistics import mean, median

SPLIT = "2026-01-01"


def load(path):
    rows = [json.loads(l) for l in open(path)]
    return [r for r in rows if not r.get("ca_fwd") and r.get("fwd_n", 0) >= 3]


def ci(vals, n=2000):
    if len(vals) < 5:
        return (None, None)
    rnd = random.Random(7)
    ms = sorted(mean(rnd.choices(vals, k=len(vals))) for _ in range(n))
    return round(ms[int(.05 * n)], 3), round(ms[int(.95 * n)], 3)


def summary(rows, label, key="R_t1"):
    filled = [r for r in rows if r.get("filled")]
    if not rows:
        print(f"{label:34s} n=0"); return
    vals = [r[key] for r in filled]
    if not vals:
        print(f"{label:34s} plans={len(rows)} filled=0"); return
    lo, hi = ci(vals)
    print(f"{label:34s} plans={len(rows):4d} filled={len(filled):4d} ({100*len(filled)/len(rows):4.0f}%) "
          f"win={100*sum(v>0 for v in vals)/len(vals):4.1f}% avgR={mean(vals):+.3f} medR={median(vals):+.2f} "
          f"90%CI=[{lo},{hi}] sumR={sum(vals):+.1f} day1stop={100*mean(r['first_day_stop'] for r in filled):.0f}%")


def buckets(rows, feat, edges, key="R_t1"):
    filled = [r for r in rows if r.get("filled") and r.get(feat) is not None]
    out = []
    for lo, hi in zip(edges, edges[1:]):
        g = [r[key] for r in filled if lo <= r[feat] < hi]
        out.append(f"[{lo},{hi}) n={len(g)} {mean(g):+.2f}" if g else f"[{lo},{hi}) n=0")
    return " | ".join(out)


FEATS = {
    "rvol": [0, 1.5, 2, 3, 100], "rsi": [0, 45, 55, 65, 72, 100], "ext_atr": [-9, 1, 2, 3, 99],
    "range_atr": [0, 1, 1.5, 2, 99], "close_loc": [0, .5, .8, .95, 1.01], "risk_pct": [0, 1.5, 2.5, 3.5, 9],
    "atr_pct": [0, 1.8, 2.5, 3.5, 99], "ema_trend": [-99, 0, .5, 1.2, 99], "oi_chg": [-99, 0, 3, 8, 999],
    "oi3": [-99, 0, 5, 12, 999], "tot_oi_pct": [-99, 0, 2, 6, 999], "dte": [0, 7, 14, 21, 99],
    "breadth": [0, .35, .5, .65, 1.01], "nifty_ret5": [-99, -1, 0, 1, 99], "nifty_ret20": [-99, -2, 0, 2, 99],
    "rs20": [-99, 0, 5, 10, 999], "rr_t1": [0, .8, 1.2, 2, 99], "pcr": [0, .5, .8, 1.1, 99],
}

if __name__ == "__main__":
    rows = load(sys.argv[1])
    key = "R_t1"
    for k in ("R_t1", "R_scaled", "R_time10"):
        print(f"\n===== metric {k} =====")
        for period, sel in (("ALL", lambda r: True), ("IS 2025", lambda r: r["date"] < SPLIT), ("OOS 2026", lambda r: r["date"] >= SPLIT)):
            for tier in ("A", "B", "C"):
                summary([r for r in rows if sel(r) and r["tier"] == tier], f"{period} tier {tier}", k)
            summary([r for r in rows if sel(r) and r["selected"]], f"{period} SHORTLISTED", k)
            summary([r for r in rows if sel(r)], f"{period} all plans", k)
    print()
    for d in ("LONG", "SHORT"):
        summary([r for r in rows if r["direction"] == d], f"dir {d}")
    for pw in sorted({(r["tier"], r["pathway"] or r["entry_pattern"]) for r in rows}):
        summary([r for r in rows if (r["tier"], r["pathway"] or r["entry_pattern"]) == pw], f"{pw[0]} {pw[1][:30]}")
    for pat in sorted({r["pattern"] for r in rows if r["pattern"]}):
        summary([r for r in rows if r["pattern"] == pat], f"pat {pat[:30]}")
    for rg in sorted({r["regime"] or "" for r in rows}):
        summary([r for r in rows if r["regime"] == rg], f"regime {rg}")
    skips = {}
    for r in rows:
        if not r.get("filled"):
            skips[r.get("skip")] = skips.get(r.get("skip"), 0) + 1
    print("unfilled reasons", skips)
    if "--features" in sys.argv:
        for period, sel in (("IS", lambda r: r["date"] < SPLIT), ("OOS", lambda r: r["date"] >= SPLIT)):
            print(f"\n--- feature buckets {period} (mean {key}) ---")
            sub = [r for r in rows if sel(r)]
            for feat, edges in FEATS.items():
                print(f"{feat:11s} {buckets(sub, feat, edges)}")
            for feat in ("nifty_above_sma20", "ca_hist"):
                for v in (True, False):
                    g = [r[key] for r in sub if r.get("filled") and r.get(feat) is v]
                    print(f"{feat}={v}: n={len(g)} {mean(g):+.3f}" if g else f"{feat}={v}: n=0")
            for d in ("LONG", "SHORT"):
                for v in (True, False):
                    g = [r[key] for r in sub if r.get("filled") and r["direction"] == d and r.get("nifty_above_sma20") is v]
                    print(f"{d} nifty_above_sma20={v}: n={len(g)} {mean(g):+.3f}" if g else "")
