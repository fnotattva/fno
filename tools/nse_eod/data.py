"""Download and validate public NSE EOD UDiFF FO/CM archives. No credentials."""
from __future__ import annotations
import csv
import io
import zipfile
import time
import urllib.request
import urllib.error
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

MAX_BYTES = 24 * 1024 * 1024
ROOT = "https://nsearchives.nseindia.com/content"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}
REQUIRED = {"TradDt", "FinInstrmTp", "TckrSymb", "ClsPric", "OpnIntrst", "ChngInOpnIntrst", "XpryDt", "StrkPric", "OptnTp", "TtlTradgVol"}
class Unavailable(RuntimeError):
    pass

def url_for(segment: str, day: date) -> str:
    tag = segment.upper()
    if tag not in ("FO", "CM"): raise ValueError("Bad segment")
    return f"{ROOT}/{tag.lower()}/BhavCopy_NSE_{tag}_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"

def _download(url: str, timeout: int = 16) -> bytes:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with opener.open(request, timeout=timeout) as response:
            host = urllib.request.urlparse(response.geturl()).hostname or ""
            if not (host == "nseindia.com" or host.endswith(".nseindia.com")):
                raise Unavailable("Redirect outside NSE")
            blob = response.read(MAX_BYTES + 1)
            if len(blob) > MAX_BYTES: raise Unavailable("Archive exceeds size cap")
            return blob
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Unavailable(f"Download failed: {type(exc).__name__}: {str(exc)[:90]}") from exc

def load(segment: str, day: date) -> list[dict[str, str]]:
    blob = _download(url_for(segment, day))
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise Unavailable("NSE response is not a ZIP")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        if archive.testzip() is not None: raise Unavailable("Corrupt ZIP")
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1: raise Unavailable("Unexpected number of CSV files")
        if archive.getinfo(names[0]).file_size > 65 * 1024 * 1024:
            raise Unavailable("CSV extraction size cap")
        with archive.open(names[0]) as item:
            rows = list(csv.DictReader(io.TextIOWrapper(item, encoding="utf-8-sig", errors="strict")))
    if not rows or not REQUIRED.issubset(rows[0]):
        raise Unavailable("Unexpected or incomplete UDiFF schema")
    observed = set(r["TradDt"] for r in rows[:1000])
    expected = {day.isoformat(), day.strftime("%d-%m-%Y"), day.strftime("%d/%m/%Y")}
    if not observed.intersection(expected):
        raise Unavailable(f"Trade date mismatch in NSE archive: {sorted(observed)[:3]}")
    if segment.upper() == "FO":
        if not any(r["FinInstrmTp"] == "STF" for r in rows):
            raise Unavailable("F&O archive missing stock futures")
        if not any(r["FinInstrmTp"] == "STO" for r in rows):
            raise Unavailable("F&O archive missing stock options")
    return rows

def most_recent(asof: date, back_days: int = 8):
    errors = []
    for n in range(back_days):
        day = asof - timedelta(days=n)
        if day.weekday() >= 5: continue
        try:
            fo = load("FO", day)
            cm = load("CM", day)
            return day, fo, cm, errors
        except Unavailable as exc:
            errors.append(f"{day.isoformat()}: {str(exc)[:120]}")
    raise Unavailable("No jointly valid FO/CM archive in lookback: " + "; ".join(errors[:5]))

def cash_history(latest: date, days: int = 47, workers: int = 8):
    history = {}
    errors = {}
    targets = [latest - timedelta(days=d) for d in range(1, days + 1)]
    targets = [d for d in targets if d.weekday() < 5]
    def task(day):
        return day, load("CM", day)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, d): d for d in targets}
        for fut in as_completed(futures):
            day = futures[fut]
            try:
                key, rows = fut.result()
                history[key] = rows
            except (Unavailable, ValueError, zipfile.BadZipFile) as exc:
                errors[day.isoformat()] = str(exc)[:110]
    return history, errors
