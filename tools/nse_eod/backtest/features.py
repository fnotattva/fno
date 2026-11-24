"""Features + forward returns on the stock-day panel (no lookahead)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import store

df = pd.read_pickle(str(store.CACHE / "panel_raw.pkl"))
df = df.dropna(subset=["o", "h", "l", "c"]).sort_values(["symbol", "date"]).reset_index(drop=True)
g = df.groupby("symbol", sort=False)
prev_c = g["c"].shift(1)
# Corporate-action breaks: open > 25% away from previous close starts a new segment.
brk = ((df["o"] / prev_c - 1).abs() > .25).fillna(False)
df["seg"] = brk.groupby(df["symbol"]).cumsum()
G = df.groupby(["symbol", "seg"], sort=False)

def sh(col, n):
    return G[col].shift(n)

df["ret1"] = df["c"] / sh("c", 1) - 1
for n in (5, 20, 60):
    df[f"ret{n}"] = df["c"] / sh("c", n) - 1
tr = np.maximum(df["h"] - df["l"], np.maximum((df["h"] - sh("c", 1)).abs(), (df["l"] - sh("c", 1)).abs()))
df["tr"] = tr
df["atr14"] = G["tr"].transform(lambda s: s.rolling(14).mean())
df["ema20"] = G["c"].transform(lambda s: s.ewm(span=20, adjust=False, min_periods=20).mean())
df["ema50"] = G["c"].transform(lambda s: s.ewm(span=50, adjust=False, min_periods=50).mean())
df["trend_atr"] = (df["ema20"] - df["ema50"]) / df["atr14"]
df["ext_atr"] = (df["c"] - df["ema20"]) / df["atr14"]
df["vol20"] = G["v"].transform(lambda s: s.shift(1).rolling(20).mean())
df["rvol"] = df["v"] / df["vol20"]
df["hi20"] = G["h"].transform(lambda s: s.shift(1).rolling(20).max())
df["lo20"] = G["l"].transform(lambda s: s.shift(1).rolling(20).min())
df["dist_hi20"] = df["c"] / df["hi20"] - 1
df["dist_lo20"] = df["c"] / df["lo20"] - 1
rng = (df["h"] - df["l"]).replace(0, np.nan)
df["close_loc"] = (df["c"] - df["l"]) / rng
df["gap"] = df["o"] / sh("c", 1) - 1
# Delivery
df["deliv_rel"] = df["deliv_pct"] / G["deliv_pct"].transform(lambda s: s.shift(1).rolling(20).mean())
df["delivq_rel"] = df["deliv_qty"] / G["deliv_qty"].transform(lambda s: s.shift(1).rolling(20).mean())
# Futures / OI (all-expiry, roll-neutral daily change)
df["fpct"] = df["fut"] / df["fut_prev"] - 1
base = df["oi_all"] - df["doi_all"]
df["oi1"] = np.where(base > 0, df["doi_all"] / base, np.nan)
fbase = df["front_oi"] - df["front_doi"]
df["front_oi1"] = np.where(fbase > 0, df["front_doi"] / fbase, np.nan)
s5 = G["doi_all"].transform(lambda s: s.rolling(5).sum())
df["oi5"] = s5 / (df["oi_all"] - s5)
s3 = G["doi_all"].transform(lambda s: s.rolling(3).sum())
df["oi3"] = s3 / (df["oi_all"] - s3)

def regime(p, o, ep=.0005, eo=.005):
    out = np.full(len(p), "NEUTRAL", dtype=object)
    up, dn, oiu, oid = p > ep, p < -ep, o > eo, o < -eo
    out[up & oiu] = "LONG BUILDUP"; out[dn & oiu] = "SHORT BUILDUP"
    out[up & oid] = "SHORT COVERING"; out[dn & oid] = "LONG UNWINDING"
    return out

df["regime1"] = regime(df["fpct"].values, df["oi1"].values)
df["regime_front"] = regime(df["fpct"].values, df["front_oi1"].values)
df["regime5"] = regime(df["ret5"].values, df["oi5"].values, ep=.005, eo=.01)
# Options
df["pcr"] = df["pe_oi"] / df["ce_oi"].replace(0, np.nan)
df["dpcr"] = df["pcr"] - sh("pcr", 1)
df["opt_flow"] = (df["dpe"] - df["dce"]) / (df["ce_oi"] + df["pe_oi"]).replace(0, np.nan)
df["ivp_chg1"] = df["ivp"] / sh("ivp", 1) - 1
df["iv_rank"] = G["ivp"].transform(lambda s: s.rolling(60, min_periods=30).rank(pct=True))
df["basis"] = df["fut"] / df["spot_fo"] - 1
df["basis_chg"] = df["basis"] - sh("basis", 1)
# Forward returns from NEXT open
no = sh("o", -1)
for h in (1, 3, 5, 10):
    df[f"fwd{h}"] = sh("c", -h) / no - 1
df["next_gap"] = no / df["c"] - 1
# Market context
mkt = df.groupby("date")["ret1"].mean().rename("mkt_ret1")
df = df.join(mkt, on="date")
breadth = df.assign(a=df["c"] > df["ema20"]).groupby("date")["a"].mean().rename("breadth")
df = df.join(breadth, on="date")
for h in (1, 3, 5, 10):
    df[f"xs{h}"] = df[f"fwd{h}"] - df.groupby("date")[f"fwd{h}"].transform("mean")
df["liquid"] = df["turnover"] >= 1.5e8 if "turnover" in df else True
df.to_pickle(str(store.CACHE / "panel.pkl"))
print(df.shape, df["fwd5"].notna().sum(), df["regime1"].value_counts().to_dict())
