"""Monthly performance monitor for the NSE EOD engine (research only).

Usage (from tools/nse_eod/backtest):
    export NSE_EOD_CACHE=~/.cache/nse_eod
    python monitor.py --months 6            # default: last 6 months

Steps: fetch the official NSE archives the window needs (plus warm-up),
replay the CURRENT engine on them with replay.py, then report rolling
results and a plain verdict:

  CONTINUE   last-60-trade average R > 0
  WATCH      last-60 average between -0.10R and 0, or too few trades
  PAUSE      last-60 average <= -0.10R, or its 90% bootstrap upper bound < 0

Reference: replay of Mar 2025 - Nov 2026 gave +0.18R per filled plan
(59% win) at a 0.15% round-trip cost assumption. EOD simulation, not P&L.
"""
import argparse, json, random, subprocess, sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
REFERENCE_R = 0.18
WINDOW = 60


def ci90(vals, n=2000):
    rnd = random.Random(11)
    ms = sorted(mean(rnd.choices(vals, k=len(vals))) for _ in range(n))
    return ms[int(.05 * n)], ms[int(.95 * n)]


def verdict(last):
    if len(last) < 20:
        return "WATCH", f"only {len(last)} filled trades in window; too few to judge"
    avg = mean(last)
    lo, hi = ci90(last)
    if avg <= -0.10 or hi < 0:
        return "PAUSE", f"last {len(last)} trades average {avg:+.3f}R (90% CI {lo:+.2f} to {hi:+.2f})"
    if avg <= 0:
        return "WATCH", f"last {len(last)} trades average {avg:+.3f}R (90% CI {lo:+.2f} to {hi:+.2f})"
    return "CONTINUE", f"last {len(last)} trades average {avg:+.3f}R (90% CI {lo:+.2f} to {hi:+.2f})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--end", default=None, help="YYYY-MM-DD, default yesterday")
    ap.add_argument("--out", default="monitor_out.jsonl")
    a = ap.parse_args()
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=1)
    start = end - timedelta(days=30 * a.months)
    warm = start - timedelta(days=125)
    subprocess.run([sys.executable, str(HERE / "fetch.py"), warm.isoformat(), end.isoformat()], check=True)
    subprocess.run([sys.executable, str(HERE / "replay.py"), str(ENGINE), a.out,
                    start.isoformat(), end.isoformat()], check=True)
    rows = [json.loads(l) for l in open(a.out)]
    rows = [r for r in rows if not r.get("ca_fwd") and r.get("fwd_n", 0) >= 3]
    filled = sorted((r for r in rows if r.get("filled")), key=lambda r: r["date"])
    complete = [r for r in filled if r.get("complete", True)]
    print(f"\n=== NSE EOD engine monitor: {start} to {end} ===")
    print(f"Plans issued: {len(rows)} | filled: {len(filled)} | fully resolved: {len(complete)}")
    if filled:
        vals = [r["R_t1"] for r in filled]
        print(f"All filled: avg {mean(vals):+.3f}R, win {100*mean(v > 0 for v in vals):.0f}% "
              f"(reference {REFERENCE_R:+.2f}R)")
        for tier in "ABC":
            g = [r["R_t1"] for r in filled if r["tier"] == tier]
            if g:
                print(f"  Tier {tier}: n={len(g)} avg {mean(g):+.3f}R win {100*mean(v > 0 for v in g):.0f}%")
        by_month = {}
        for r in filled:
            by_month.setdefault(r["date"][:7], []).append(r["R_t1"])
        for m, g in sorted(by_month.items()):
            print(f"  {m}: n={len(g)} avg {mean(g):+.3f}R")
    last = [r["R_t1"] for r in complete][-WINDOW:]
    v, why = verdict(last)
    print(f"\nVERDICT: {v} - {why}")
    print("Historical EOD simulation (0.15% cost, stop-first on ambiguous bars). Not realised P&L.")


if __name__ == "__main__":
    main()
