"""Parse cached NSE ZIPs into compact pickles (only columns the engine reads)."""
import csv, io, os, pickle, zipfile, sys
from pathlib import Path
from datetime import date

CACHE = Path(os.environ.get("NSE_EOD_CACHE", Path.home() / ".cache" / "nse_eod"))
PK = CACHE / "pk"
CM_COLS = ("TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric",
           "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal")
FO_COLS = ("TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "OpnPric",
           "HghPric", "LwPric", "ClsPric", "SttlmPric", "PrvsClsgPric", "OpnIntrst",
           "ChngInOpnIntrst", "TtlTradgVol", "UndrlygPric")

def _rows(path):
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))

def days(seg):
    return sorted(date(int(p.stem[:4]), int(p.stem[4:6]), int(p.stem[6:])) for p in (CACHE / seg).glob("*.zip"))

def cm(d):
    p = PK / "cm" / f"{d:%Y%m%d}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    rows = [{k: r.get(k, "") for k in CM_COLS} for r in _rows(CACHE / "cm" / f"{d:%Y%m%d}.zip")
            if r.get("SctySrs") == "EQ"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(rows))
    return rows

def fo(d):
    p = PK / "fo" / f"{d:%Y%m%d}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    rows = [{k: r.get(k, "") for k in FO_COLS} for r in _rows(CACHE / "fo" / f"{d:%Y%m%d}.zip")
            if r.get("FinInstrmTp") in ("STF", "STO", "IDF")]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pickle.dumps(rows))
    return rows
