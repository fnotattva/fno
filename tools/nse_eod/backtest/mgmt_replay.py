"""Replay the engine's daily lifecycle management on every fresh plan.

Usage: python3 mgmt_replay.py .. out.jsonl [START] [END]   (ENGINE_DIR = tools/nse_eod)

For each plan issued by build_market_summary, the production function
management.review_research_plans is called on EVERY later session with that
day's snapshots, exactly as runner.main does. Its advice is then executed with
EOD discipline: exits advised at EOD happen at the NEXT session's open; a
suggested stop applies from the next session; time exit at the close of the
10th holding session. Several exit variants consume the same advice stream.
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
from management import review_research_plans   # noqa: E402
from logic import classify_futures, pct        # noqa: E402

HIST = 72
COST = 0.0015
VALID = 2
MAX_HOLD = 10


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


class Pos:
    """One execution variant of one plan."""
    def __init__(self, name, plan, take_t1, half, use_mgmt, use_t3):
        self.name, self.p = name, plan
        self.take_t1, self.half, self.use_mgmt, self.use_t3 = take_t1, half, use_mgmt, use_t3
        self.side = 1 if plan["direction"] == "LONG" else -1
        self.e, self.s0 = plan["entry_trigger"], plan["stop_loss"]
        self.risk = abs(self.e - self.s0)
        self.stop = self.s0
        self.weight = 1.0
        self.realized = 0.0
        self.fill = None
        self.k = 0
        self.pending_exit = False
        self.done = False
        self.reason = None
        self.t1_done = False

    def _close(self, px, w, why):
        self.realized += w * self.side * (px - self.fill) / self.risk
        self.weight -= w
        if self.weight <= 1e-9:
            self.done, self.reason = True, why

    def better(self, a, b):           # tighter protective stop
        return max(a, b) if self.side > 0 else min(a, b)

    def day(self, b, first):
        """Process one session bar after fill. first=True on the fill day."""
        side = self.side
        self.k += 1
        if not first:
            if self.pending_exit:
                self._close(b["o"], self.weight, "mgmt exit next open"); return
            if side * (b["o"] - self.stop) <= 0:
                self._close(b["o"], self.weight, "gap through stop"); return
        if (b["l"] <= self.stop) if side > 0 else (b["h"] >= self.stop):
            self._close(self.stop, self.weight, "stop"); return
        t1, t3 = self.p["target_1"], self.p["target_3"]
        if self.take_t1 and not self.t1_done and ((b["h"] >= t1) if side > 0 else (b["l"] <= t1)):
            px = b["o"] if (not first and side * (b["o"] - t1) >= 0) else t1
            w = .5 if self.half else self.weight
            self._close(px, w, "T1")
            self.t1_done = True
            if self.half and not self.done:
                self.stop = self.better(self.stop, self.fill + side * COST * self.fill)
            if self.done:
                return
        if self.use_t3 and ((b["h"] >= t3) if side > 0 else (b["l"] <= t3)):
            px = b["o"] if (not first and side * (b["o"] - t3) >= 0) else t3
            self._close(px, self.weight, "T3"); return
        if self.k >= MAX_HOLD:
            self._close(b["c"], self.weight, "time exit day 10")

    def advice(self, upd):
        if self.done or self.fill is None or not self.use_mgmt or not upd:
            return
        sug = upd.get("suggested_stop_next_session_if_filled")
        if sug:
            self.stop = self.better(self.stop, float(sug))
        act = str(upd.get("action_if_filled", ""))
        if upd.get("terminal_for_scenario") and ("EXIT" in act or "CLOSE" in act) and "TIME EXIT" not in act:
            self.pending_exit = True
            self.exit_rule = act[:60]
        elif ("REDUCE/EXIT" in act) and self.use_mgmt == "strict":
            self.pending_exit = True

    def result(self):
        cost_r = COST * self.fill / self.risk
        return round(self.realized - cost_r, 3), self.reason, self.k


VARIANTS = (
    ("V0_T1_only", dict(take_t1=True, half=False, use_mgmt=False, use_t3=False)),
    ("V1_T1_plus_mgmt", dict(take_t1=True, half=False, use_mgmt=True, use_t3=False)),
    ("V1s_T1_plus_mgmt_strict", dict(take_t1=True, half=False, use_mgmt="strict", use_t3=False)),
    ("V2_mgmt_to_T3", dict(take_t1=False, half=False, use_mgmt=True, use_t3=True)),
    ("V3_half_T1_rest_mgmt", dict(take_t1=True, half=True, use_mgmt=True, use_t3=True)),
    ("V4_stop_T3_day10", dict(take_t1=False, half=False, use_mgmt=False, use_t3=True)),
)


def try_fill(p, b, side):
    """Same entry rules as replay.simulate. Returns (status, px)."""
    e, s, gap = p["entry_trigger"], p["stop_loss"], p.get("gap_skip_level")
    pullback = side * (e - p["cash_close"]) < 0
    o, h, l = b["o"], b["h"], b["l"]
    if side * (o - s) <= 0:
        return "cancel", None
    if pullback:
        if (l <= e) if side > 0 else (h >= e):
            return "fill", (e if side * (o - e) >= 0 else o)
        return "wait", None
    if gap and side * (o - gap) > 0:
        return "cancel", None
    if side * (o - e) >= 0:
        return "fill", o
    if (h >= e) if side > 0 else (l <= e):
        return "fill", e
    return "wait", None


def main():
    out = Path(sys.argv[2])
    start = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date(2025, 3, 20)
    end = date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else date(2026, 11, 23)
    days = sorted(set(store.days("cm")) & set(store.days("fo")))
    cm = {d: store.cm(d) for d in days}
    bars = defaultdict(dict)
    for d in days:
        for r in cm[d]:
            bars[r["TckrSymb"]][d] = {"o": f(r["OpnPric"]), "h": f(r["HghPric"]), "l": f(r["LwPric"]), "c": f(r["ClsPric"])}
    regimes = {}                      # date -> {(sym, expiry): regime}
    live = []                         # dicts: plan, state, positions, sessions, fill_status
    results = []
    t0 = time.time()
    for i, d in enumerate(days):
        if i < HIST:
            continue
        fo = store.fo(d)
        rg = {}
        for r in fo:
            if r["FinInstrmTp"] == "STF":
                oi, doi = f(r["OpnIntrst"]), f(r["ChngInOpnIntrst"])
                st, pst = f(r["SttlmPric"]) or f(r["ClsPric"]), f(r["PrvsClsgPric"])
                if oi - doi > 0 and pst > 0:
                    rg[(r["TckrSymb"], r["XpryDt"][:10])] = classify_futures(pct(st, pst), pct(oi, oi - doi))
        regimes[d] = rg
        if d < start or d > end:
            if not live:
                continue
        hist = {days[j]: cm[days[j]] for j in range(i - HIST, i)}
        picks, plans, c_plans, *_rest, snaps = runner.build_market_summary(d, fo, cm[d], hist)
        stocks = {r["TckrSymb"]: r for r in cm[d]}
        # 1) execution on today's bar for plans issued earlier
        for L in live:
            if L["closed"]:
                continue
            p, sym = L["plan"], L["plan"]["symbol"]
            b = bars[sym].get(d)
            if not b:
                continue
            side = 1 if p["direction"] == "LONG" else -1
            if L["fill"] is None:
                L["sessions"] += 1
                st, px = try_fill(p, b, side)
                if st == "cancel" or (st == "wait" and L["sessions"] >= VALID):
                    L["closed"] = True; L["fill"] = False; continue
                if st == "fill":
                    L["fill"] = px
                    for P in L["pos"]:
                        P.fill = px
                        P.day(b, True)
                continue
            for P in L["pos"]:
                if not P.done:
                    P.day(b, False)
        # 2) EOD management review for every live plan (as runner.main does)
        prior = [L["state"] for L in live if not L["closed"] and not L.get("mgmt_done")]
        if prior:
            trails = {}
            prev_days = [x for x in days[:i]][-5:] + [d]
            for st in prior:
                sym = st["signal"]["symbol"]
                fut = (snaps.get(sym) or {}).get("future") or {}
                ex = str(fut.get("XpryDt", ""))[:10]
                trails[sym] = [{"date": x.isoformat(), "status": "VERIFIED NSE FO EOD",
                                "futures_regime": regimes.get(x, {}).get((sym, ex))}
                               for x in prev_days if (sym, ex) in regimes.get(x, {})]
            updates, still = review_research_plans(prior, d, stocks, snaps, derivatives_trails=trails)
            by_id = {u["id"]: u for u in updates}
            still_ids = {s["signal"]["signal_id"]: s for s in still}
            for L in live:
                sid = L["plan"]["signal_id"]
                if sid in by_id:
                    for P in L["pos"]:
                        P.advice(by_id[sid])
                if sid in still_ids:
                    L["state"] = still_ids[sid]
                elif sid in by_id:
                    L["mgmt_done"] = True
        # 3) finished plans -> results
        for L in live:
            if L["fill"] and not L.get("reported") and all(P.done for P in L["pos"]):
                rec = {"date": L["date"], "symbol": L["plan"]["symbol"], "tier": L["tier"],
                       "direction": L["plan"]["direction"]}
                for P in L["pos"]:
                    r, why, k = P.result()
                    rec[P.name] = r; rec[P.name + "_why"] = why; rec[P.name + "_days"] = k
                    rec[P.name + "_rule"] = getattr(P, "exit_rule", None)
                results.append(rec); L["reported"] = True
        live = [L for L in live if not (L["closed"] or L.get("reported"))]
        # 4) new plans issued today
        if start <= d <= end:
            for tier, group in (("A", picks), ("B", plans), ("C", c_plans)):
                for p in group:
                    live.append({"plan": p, "tier": tier, "date": d.isoformat(), "sessions": 0, "fill": None,
                                 "closed": False,
                                 "state": {"asof_date": d.isoformat(), "last_checked": d.isoformat(),
                                           "observed_sessions": 0, "signal": p},
                                 "pos": [Pos(n, p, **kw) for n, kw in VARIANTS]})
        if i % 40 == 0:
            print(d, len(results), f"{time.time() - t0:.0f}s", flush=True)
    with out.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    print("done", len(results))


if __name__ == "__main__":
    main()
