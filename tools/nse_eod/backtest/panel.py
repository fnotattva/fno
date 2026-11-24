"""Build a stock-day panel for every NSE F&O stock from cached official archives.

Output: $NSE_EOD_CACHE/panel_raw.pkl with one row per (date, symbol).
"""
import sys, pickle
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from math import sqrt
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import store

DELIV = store.CACHE / "deliv"


def f(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


def exp(r):
    try:
        return date.fromisoformat(r["XpryDt"][:10])
    except ValueError:
        return date.min


def day_rows(d):
    fo = store.fo(d)
    fut = defaultdict(list)
    opt = defaultdict(list)
    nifty = None
    for r in fo:
        t = r["FinInstrmTp"]
        if t == "STF":
            fut[r["TckrSymb"]].append(r)
        elif t == "STO":
            opt[(r["TckrSymb"], r["XpryDt"][:10])].append(r)
        elif t == "IDF" and r["TckrSymb"] == "NIFTY":
            if nifty is None or r["XpryDt"] < nifty["XpryDt"]:
                nifty = r
    out = []
    for sym, rows in fut.items():
        rows = sorted(rows, key=exp)
        front = rows[0]
        later = [x for x in rows if (exp(x) - d).days > 3]
        ana = later[0] if (exp(front) - d).days <= 3 and later else front
        oi_all = sum(f(x["OpnIntrst"]) for x in rows)
        doi_all = sum(f(x["ChngInOpnIntrst"]) for x in rows)
        spot = f(ana["UndrlygPric"])
        ex = ana["XpryDt"][:10]
        chain = opt.get((sym, ex), [])
        ce = pe = dce = dpe = 0.0
        strikes = defaultdict(lambda: {"CE": None, "PE": None, "ceoi": 0.0, "peoi": 0.0})
        for o in chain:
            k = f(o["StrkPric"]); side = o["OptnTp"]
            oi = f(o["OpnIntrst"]); doi = f(o["ChngInOpnIntrst"])
            if side == "CE":
                ce += oi; dce += doi; strikes[k]["ceoi"] += oi
            else:
                pe += oi; dpe += doi; strikes[k]["peoi"] += oi
            strikes[k][side] = f(o["ClsPric"])
        straddle = callwall = putwall = None
        if strikes and spot > 0:
            atm = min(strikes, key=lambda k: abs(k - spot))
            c, p = strikes[atm]["CE"], strikes[atm]["PE"]
            if c and p and c > 0 and p > 0:
                straddle = (c + p) / spot
            above = [(k, v["ceoi"]) for k, v in strikes.items() if k > spot]
            below = [(k, v["peoi"]) for k, v in strikes.items() if k < spot]
            if above:
                callwall = max(above, key=lambda kv: kv[1])[0] / spot - 1
            if below:
                putwall = 1 - max(below, key=lambda kv: kv[1])[0] / spot
        dte = max((date.fromisoformat(ex) - d).days, 1)
        out.append({
            "date": d, "symbol": sym,
            "fut": f(ana["SttlmPric"]) or f(ana["ClsPric"]), "fut_prev": f(ana["PrvsClsgPric"]),
            "fut_vol": f(ana["TtlTradgVol"]), "spot_fo": spot,
            "front_oi": f(ana["OpnIntrst"]), "front_doi": f(ana["ChngInOpnIntrst"]),
            "oi_all": oi_all, "doi_all": doi_all, "dte": dte, "rolled": ana is not front,
            "ce_oi": ce, "pe_oi": pe, "dce": dce, "dpe": dpe,
            "straddle": straddle, "ivp": (straddle / (0.8 * sqrt(dte / 365))) if straddle else None,
            "callwall_dist": callwall, "putwall_dist": putwall,
            "nifty": (f(nifty["SttlmPric"]) if nifty else None),
        })
    cm = {r["TckrSymb"]: r for r in store.cm(d)}
    deliv = {}
    p = DELIV / f"{d:%Y%m%d}.csv"
    if p.exists():
        for line in p.read_text().splitlines()[1:]:
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 15 and parts[1] == "EQ":
                deliv[parts[0]] = (f(parts[13]), f(parts[14]))
    for r in out:
        c = cm.get(r["symbol"])
        if c:
            r.update(o=f(c["OpnPric"]), h=f(c["HghPric"]), l=f(c["LwPric"]), c=f(c["ClsPric"]),
                     v=f(c["TtlTradgVol"]), turnover=f(c.get("TtlTrfVal")))
        dq = deliv.get(r["symbol"])
        r["deliv_qty"], r["deliv_pct"] = dq if dq else (None, None)
    return out


if __name__ == "__main__":
    days = sorted(set(store.days("cm")) & set(store.days("fo")))
    rows = []
    with ProcessPoolExecutor(2) as pool:
        for i, part in enumerate(pool.map(day_rows, days, chunksize=4)):
            rows += part
            if i % 50 == 0:
                print(i, len(rows), flush=True)
    df = pd.DataFrame(rows)
    df.to_pickle(str(store.CACHE / "panel_raw.pkl"))
    print(df.shape, df["date"].min(), df["date"].max(), df["deliv_pct"].notna().mean())
