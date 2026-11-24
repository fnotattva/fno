"""Day-by-day replay of the production NSE EOD engine on cached official archives.

Usage: python3 replay.py ../ out.jsonl [START] [END]   (ENGINE_DIR = tools/nse_eod)
Imports build_market_summary from ENGINE_DIR (unchanged production code or a
candidate variant), records every pre-shortlist A/B/C plan with context
features, and simulates forward outcomes on later official CM bars.
"""
import json, sys, time
from collections import defaultdict
from datetime import date
from pathlib import Path

ENGINE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).parent))
import store                                   # noqa: E402
import runner                                  # noqa: E402
from shortlist import choose_daily_shortlist  # noqa: E402

HIST_SESSIONS = 72      # production cash_history stops at >=70 in 12-day batches
COST = 0.0015
VALID = 2
MAX_HOLD = 10
FWD = VALID + MAX_HOLD + 1


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def simulate(p, bars):
    """Conservative EOD simulation. bars: forward CM rows (dict o,h,l,c,pc)."""
    side = 1 if p["direction"] == "LONG" else -1
    e, s = p["entry_trigger"], p["stop_loss"]
    t1, t2, t3 = p["target_1"], p["target_2"], p["target_3"]
    gap = p.get("gap_skip_level")
    risk = abs(e - s)
    cost_r = COST * e / risk
    pullback = side * (e - p["cash_close"]) < 0
    res = {"filled": False, "skip": None}
    fill_i = fill_px = None
    for i, b in enumerate(bars[:VALID]):
        o, h, l = b["o"], b["h"], b["l"]
        if side * (o - s) <= 0:
            res["skip"] = "open beyond stop"; return res
        if pullback:
            if side * (l - e) <= 0 if side > 0 else side * (h - e) <= 0:
                fill_i, fill_px = i, (e if side * (o - e) >= 0 else o)
                break
        else:
            if gap and side * (o - gap) > 0:
                res["skip"] = "gap beyond skip level"; return res
            if side * (o - e) >= 0:
                fill_i, fill_px = i, o; break
            if (h >= e) if side > 0 else (l <= e):
                fill_i, fill_px = i, e; break
    if fill_i is None:
        res["skip"] = res["skip"] or "not triggered"; return res
    res.update(filled=True, fill_day=fill_i + 1, fill_px=fill_px)
    path = bars[fill_i:fill_i + MAX_HOLD]

    def hit(b, lvl, fav):   # fav: favourable direction touch
        return (b["h"] >= lvl) if (side > 0) == fav else (b["l"] <= lvl)

    def run(targets_w, be_after_first):
        """targets_w: list of (target, weight). Returns R incl. costs."""
        remaining = list(targets_w)
        stop = s
        total = 0.0
        out_day = None
        for k, b in enumerate(path):
            if not remaining:
                break
            if k > 0 and side * (b["o"] - stop) <= 0:            # gap through stop
                total += sum(w for _, w in remaining) * side * (b["o"] - fill_px) / risk
                remaining = []; out_day = k + 1; break
            stop_touch = hit(b, stop, False)
            if stop_touch:
                total += sum(w for _, w in remaining) * side * (stop - fill_px) / risk
                remaining = []; out_day = k + 1; break
            new = []
            for t, w in remaining:
                if hit(b, t, True):
                    px = b["o"] if (k > 0 and side * (b["o"] - t) >= 0) else t
                    total += w * side * (px - fill_px) / risk
                    if be_after_first:
                        stop = fill_px + side * COST * fill_px
                else:
                    new.append((t, w))
            remaining = new
            if not remaining:
                out_day = k + 1
        if remaining:
            last = path[-1]
            total += sum(w for _, w in remaining) * side * (last["c"] - fill_px) / risk
            out_day = len(path)
        return round(total - cost_r, 3), out_day

    res["R_1R"], _ = run([(fill_px + side * risk, 1.0)], False)
    res["R_1p5R"], _ = run([(fill_px + side * 1.5 * risk, 1.0)], False)
    near = t1 if side * (t1 - (fill_px + side * 1.2 * risk)) < 0 else fill_px + side * 1.2 * risk
    res["R_t1cap"], _ = run([(near, 1.0)], False)
    res["R_half1R_trail"], _ = run([(fill_px + side * risk, .5), (t2, .5)], True)
    res["R_t1"], res["days_t1"] = run([(t1, 1.0)], False)
    res["R_scaled"], res["days_scaled"] = run([(t1, .5), (t2, .25), (t3, .25)], True)
    res["R_time10"] = round(side * (path[-1]["c"] - fill_px) / risk - cost_r, 3)
    res["complete"] = len(path) >= MAX_HOLD
    hi = max((side * ((b["h"] if side > 0 else b["l"]) - fill_px)) for b in path)
    lo = min((side * ((b["l"] if side > 0 else b["h"]) - fill_px)) for b in path)
    res["mfe_R"], res["mae_R"] = round(hi / risk, 2), round(lo / risk, 2)
    res["first_day_stop"] = hit(path[0], s, False)
    res.update(confirm_variant(p, bars))
    return res


def confirm_variant(p, bars):
    """EOD proxy for a confirmation rule: a session must CLOSE beyond the
    trigger (breakout) or back above/below it after touching (pullback);
    entry at the following session's open, original stop/T1, 10-session cap."""
    side = 1 if p["direction"] == "LONG" else -1
    e, s, t1 = p["entry_trigger"], p["stop_loss"], p["target_1"]
    risk = abs(e - s)
    for i, b in enumerate(bars[:VALID]):
        if side * (b["l" if side > 0 else "h"] - s) <= 0:
            return {"conf_filled": False}
        touched = (b["h"] >= e) if side > 0 else (b["l"] <= e)
        if touched and side * (b["c"] - e) > 0:
            if i + 1 >= len(bars):
                return {"conf_filled": False}
            nxt = bars[i + 1]
            px = nxt["o"]
            if side * (px - s) <= 0 or side * (px - (e + side * .5 * risk)) > 0:
                return {"conf_filled": False}
            r = abs(px - s)
            cost_r = COST * px / r
            for b2 in bars[i + 1:i + 1 + MAX_HOLD]:
                if side * (b2["o"] - s) <= 0:
                    return {"conf_filled": True, "R_conf": round(side * (b2["o"] - px) / r - cost_r, 3)}
                if (b2["l"] <= s) if side > 0 else (b2["h"] >= s):
                    return {"conf_filled": True, "R_conf": round(-1 - cost_r, 3)}
                if (b2["h"] >= t1) if side > 0 else (b2["l"] <= t1):
                    return {"conf_filled": True, "R_conf": round(side * (t1 - px) / r - cost_r, 3)}
            last = bars[i + 1:i + 1 + MAX_HOLD][-1]
            return {"conf_filled": True, "R_conf": round(side * (last["c"] - px) / r - cost_r, 3)}
    return {"conf_filled": False}


def main():
    out = Path(sys.argv[2])
    start = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date(2025, 3, 20)
    end = date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else date(2026, 11, 23)
    cm_days = store.days("cm")
    fo_days = set(store.days("fo"))
    days = [d for d in cm_days if d in fo_days]
    cm = {}
    for d in days:
        cm[d] = store.cm(d)
    bars = defaultdict(dict)       # sym -> date -> bar
    for d in days:
        for r in cm[d]:
            bars[r["TckrSymb"]][d] = {"o": f(r["OpnPric"]), "h": f(r["HghPric"]), "l": f(r["LwPric"]),
                                      "c": f(r["ClsPric"]), "pc": f(r["PrvsClsgPric"]),
                                      "v": f(r["TtlTradgVol"])}
    nifty = []
    fo_mem = {}                    # date -> {(sym, expiry): (oi, settle)}
    t0 = time.time()
    n_out = 0
    with out.open("w") as fh:
        for i, d in enumerate(days):
            fo = store.fo(d)
            idf = [r for r in fo if r["FinInstrmTp"] == "IDF" and r["TckrSymb"] == "NIFTY"]
            if idf:
                nifty.append((d, f(min(idf, key=lambda r: r["XpryDt"])["SttlmPric"])))
            snap = defaultdict(lambda: [0.0, 0.0])
            for r in fo:
                if r["FinInstrmTp"] == "STF":
                    fo_mem.setdefault(d, {})[(r["TckrSymb"], r["XpryDt"][:10])] = (f(r["OpnIntrst"]), f(r["SttlmPric"]))
                    snap[r["TckrSymb"]][0] += f(r["OpnIntrst"])
                    snap[r["TckrSymb"]][1] += f(r["ChngInOpnIntrst"])
            if d < start or d > end or i < HIST_SESSIONS:
                continue
            hist = {days[j]: cm[days[j]] for j in range(i - HIST_SESSIONS, i)}
            (picks, plans, c_plans, watch, obs, cov, regimes, nf, snaps) = runner.build_market_summary(d, fo, cm[d], hist)
            sel_a, sel_b, sel_c, _ = choose_daily_shortlist(picks, plans, c_plans)
            selected = {x["signal_id"] for x in sel_a + sel_b + sel_c}
            techs = [s["tech"] for s in snaps.values()]
            breadth = sum(t["close"] > t["ema20"] for t in techs) / max(1, len(techs))
            ncl = [c for _, c in nifty]
            n_ema = None
            if len(ncl) >= 20:
                a = sum(ncl[-20:]) / 20
                n_ema = a
            nifty_ret5 = (ncl[-1] / ncl[-6] - 1) * 100 if len(ncl) > 6 else None
            nifty_ret20 = (ncl[-1] / ncl[-21] - 1) * 100 if len(ncl) > 21 else None
            prev_days = [x for x in days[:i]][-3:]
            fwd_days = days[i + 1:i + 1 + FWD]
            for tier, group in (("A", picks), ("B", plans), ("C", c_plans)):
                for p in group:
                    sym = p["symbol"]
                    sn = snaps.get(sym, {})
                    tech = sn.get("tech") or {}
                    fut = sn.get("future") or {}
                    ex = fut.get("XpryDt", "")[:10]
                    side = 1 if p["direction"] == "LONG" else -1
                    oi3 = None
                    if prev_days and ex and (sym, ex) in fo_mem.get(prev_days[0], {}):
                        old = fo_mem[prev_days[0]][(sym, ex)][0]
                        oi3 = (f(fut.get("OpnIntrst")) / old - 1) * 100 if old > 0 else None
                    sb = bars[sym]
                    hd = [days[j] for j in range(i - HIST_SESSIONS, i + 1) if days[j] in sb]
                    ca_hist = any(abs(sb[b]["o"] / sb[a]["c"] - 1) > .25 for a, b in zip(hd, hd[1:]) if sb[a]["c"] > 0 and sb[b]["o"] > 0)
                    ret20 = (sb[d]["c"] / sb[hd[-21]]["c"] - 1) * 100 if len(hd) > 21 else None
                    tot = snap.get(sym, [0, 0])
                    tot_oi_pct = tot[1] / (tot[0] - tot[1]) * 100 if tot[0] - tot[1] > 0 else None
                    fwd = [sb[x] for x in fwd_days if x in sb]
                    ca_fwd = any(abs(b2["o"] / b1["c"] - 1) > .25 for b1, b2 in zip([sb[d]] + fwd, fwd) if b1["c"] > 0 and b2["o"] > 0)
                    rec = {
                        "date": d.isoformat(), "tier": tier, "symbol": sym, "direction": p["direction"],
                        "selected": p["signal_id"] in selected,
                        "pathway": p.get("research_pathway", ""), "pattern": p.get("pattern", p.get("regime")),
                        "entry_pattern": p.get("entry_pattern", "breakout"),
                        "entry": p["entry_trigger"], "stop": p["stop_loss"], "t1": p["target_1"],
                        "rr_t1": p["modelled_net_rr_t1"],
                        "risk_pct": round(100 * abs(p["entry_trigger"] - p["stop_loss"]) / p["entry_trigger"], 2),
                        "rvol": tech.get("rvol20"), "rsi": tech.get("rsi14"),
                        "ext_atr": side * (tech["close"] - tech["ema20"]) / tech["atr14"] if tech else None,
                        "range_atr": (tech["high"] - tech["low"]) / tech["atr14"] if tech else None,
                        "close_loc": (tech["close"] - tech["low"]) / (tech["high"] - tech["low"]) if tech and tech["high"] > tech["low"] else None,
                        "atr_pct": 100 * tech["atr14"] / tech["close"] if tech else None,
                        "ema_trend": side * (tech["ema20"] - tech["ema50"]) / tech["atr14"] if tech else None,
                        "fut_chg": p.get("futures_change_pct"), "oi_chg": p.get("futures_oi_change_pct"),
                        "oi3": oi3, "tot_oi_pct": tot_oi_pct, "regime": p.get("futures_regime", p.get("regime")),
                        "dte": (date.fromisoformat(ex) - d).days if ex else None,
                        "breadth": breadth, "nifty_above_sma20": (ncl[-1] > n_ema) if n_ema else None,
                        "nifty_ret5": nifty_ret5, "nifty_ret20": nifty_ret20,
                        "rs20": (ret20 - nifty_ret20) * side if ret20 is not None and nifty_ret20 is not None else None,
                        "pcr": (sn.get("chain") or {}).get("pcr"),
                        "ca_hist": ca_hist, "ca_fwd": ca_fwd,
                        "fwd_n": len(fwd),
                    }
                    rec.update(simulate(p, fwd) if fwd else {"filled": False, "skip": "no forward data"})
                    fh.write(json.dumps(rec) + "\n")
                    n_out += 1
            if i % 20 == 0:
                print(d, n_out, f"{time.time() - t0:.0f}s", flush=True)
    print("done", n_out)


if __name__ == "__main__":
    main()
