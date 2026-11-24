"""Download and validate public NSE EOD UDiFF FO/CM archives. No credentials."""
from __future__ import annotations
import csv
import io
import zipfile
import time
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

MAX_BYTES = 24 * 1024 * 1024
ROOT = "https://nsearchives.nseindia.com/content"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}
REQUIRED = {"TradDt", "FinInstrmTp", "TckrSymb", "ClsPric", "OpnIntrst", "ChngInOpnIntrst", "XpryDt", "StrkPric", "OptnTp", "TtlTradgVol"}
# NSE equity and equity-derivatives trading holidays for 2026.
# Official circulars: NSE/CMTR/71775 and NSE/FAOP/71777 (12 Dec 2025).
# 15 Jan closure was added in the current NSE exchange holiday calendar.
# Update from the official exchange calendar for each subsequent year.
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 15): "Municipal Corporation Election - Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}

# Special weekend sessions with official NSE UDiFF CM/FO archives published.
# These are real trading sessions and must be part of the price history;
# skipping them leaves a hole in every stock's OHLCV series. Verify each
# year's Budget-day and Muhurat sessions against NSE circulars.
NSE_SPECIAL_SESSIONS_2026 = {
    date(2026, 2, 1): "Union Budget special live trading session (Sunday)",
    date(2026, 11, 8): "Diwali Muhurat trading session (Sunday)",
}

def history_session(day: date) -> bool:
    """True when an official archive should exist for price history:
    regular sessions plus listed special (Budget/Muhurat) sessions."""
    return day in NSE_SPECIAL_SESSIONS_2026 or not market_closure(day)

def market_closure(day: date) -> str | None:
    """Return a verified regular NSE cash/F&O closure, or None if not listed.

    Weekends are not regular sessions; special Muhurat sessions require
    separately verified exchange handling and are not silently treated as
    normal trading days.
    """
    if day.weekday() >= 5:
        return "Weekend (no regular NSE cash/F&O session)"
    return NSE_HOLIDAYS_2026.get(day)

class Unavailable(RuntimeError):
    pass

def url_for(segment: str, day: date) -> str:
    tag = segment.upper()
    if tag not in ("FO", "CM"): raise ValueError("Bad segment")
    return f"{ROOT}/{tag.lower()}/BhavCopy_NSE_{tag}_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"

def _download(url: str, timeout: int = 16, attempts: int = 3) -> bytes:
    """Download once successfully, with bounded retries for transient NSE responses."""
    last_error = None
    attempts_used = 0
    for attempt in range(attempts):
        attempts_used = attempt + 1
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with opener.open(request, timeout=timeout) as response:
                host = urllib.parse.urlsplit(response.geturl()).hostname or ""
                if not (host == "nseindia.com" or host.endswith(".nseindia.com")):
                    raise Unavailable("Redirect outside NSE")
                blob = response.read(MAX_BYTES + 1)
                if len(blob) > MAX_BYTES: raise Unavailable("Archive exceeds size cap")
                return blob
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (403, 408, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(0.75 * (2 ** attempt))
    raise Unavailable(
        f"Download failed after {attempts_used} attempt(s): "
        f"{type(last_error).__name__}: {str(last_error)[:90]}"
    ) from last_error

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

DELIVERY_ROOT = "https://nsearchives.nseindia.com/products/content"

def delivery_url(day: date) -> str:
    return f"{DELIVERY_ROOT}/sec_bhavdata_full_{day:%d%m%Y}.csv"

def load_delivery(day: date) -> dict[str, float]:
    """Official NSE security-wise delivery % (EQ series) for one session.

    Context only. Raises Unavailable on any download/format problem so callers
    can record the gap instead of inventing values.
    """
    blob = _download(delivery_url(day))
    text = blob.decode("utf-8-sig", errors="strict")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or "DELIV_PER" not in [c.strip() for c in rows[0]]:
        raise Unavailable("Unexpected delivery file schema")
    head = [c.strip() for c in rows[0]]
    i_sym, i_ser, i_date, i_del = (head.index(k) for k in ("SYMBOL", "SERIES", "DATE1", "DELIV_PER"))
    out = {}
    for r in rows[1:]:
        if len(r) <= i_del or r[i_ser].strip() != "EQ":
            continue
        try:
            when = datetime.strptime(r[i_date].strip(), "%d-%b-%Y").date()
            pct_value = float(r[i_del].strip())
        except ValueError:
            continue
        if when != day:
            raise Unavailable(f"Delivery file date mismatch: {when}")
        out[r[i_sym].strip()] = pct_value
    if not out:
        raise Unavailable("Delivery file has no EQ rows")
    return out

def delivery_history(days: list[date], workers: int = 3):
    """Best-effort delivery % for several sessions: ({day: {sym: pct}}, errors)."""
    found, errors = {}, {}
    def task(day):
        return day, load_delivery(day)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, d): d for d in days}
        for fut in as_completed(futures):
            day = futures[fut]
            try:
                key, rows = fut.result()
                found[key] = rows
            except (Unavailable, ValueError, UnicodeDecodeError) as exc:
                errors[day.isoformat()] = str(exc)[:160]
    return found, errors

def most_recent(asof: date, back_days: int = 8):
    errors = []
    for n in range(back_days):
        day = asof - timedelta(days=n)
        if market_closure(day): continue
        try:
            fo = load("FO", day)
            cm = load("CM", day)
            return day, fo, cm, errors
        except Unavailable as exc:
            errors.append(f"{day.isoformat()}: {str(exc)[:120]}")
    raise Unavailable("No jointly valid FO/CM archive in lookback: " + "; ".join(errors[:5]))

def cash_history(latest: date, days: int = 115, workers: int = 3,
                 minimum_sessions: int = 70, batch_size: int = 12):
    """Fetch recent CM history in small batches until technical coverage is sufficient."""
    history = {}
    errors = {}
    targets = [latest - timedelta(days=d) for d in range(1, days + 1)]
    targets = [d for d in targets if history_session(d)]
    def task(day):
        return day, load("CM", day)
    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(task, d): d for d in batch}
            for fut in as_completed(futures):
                day = futures[fut]
                try:
                    key, rows = fut.result()
                    history[key] = rows
                except (Unavailable, ValueError, zipfile.BadZipFile) as exc:
                    errors[day.isoformat()] = str(exc)[:220]
        if len(history) >= minimum_sessions:
            break
    return history, errors


