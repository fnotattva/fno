"""Cache official NSE UDiFF CM/FO bhavcopy ZIPs for offline replay.

Usage: python fetch.py 2024-12-01 2026-11-23   (cache dir: $NSE_EOD_CACHE)
Polite: 3 workers, retries with backoff. ~1.7 MB per session (CM+FO).
"""
import os, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

CACHE = Path(os.environ.get("NSE_EOD_CACHE", Path.home() / ".cache" / "nse_eod"))
HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0",
       "Referer": "https://www.nseindia.com/all-reports-derivatives"}

def url(seg, d):
    return f"https://nsearchives.nseindia.com/content/{seg}/BhavCopy_NSE_{seg.upper()}_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"

def get(job):
    seg, d = job
    out = CACHE / seg / f"{d:%Y%m%d}.zip"
    miss = CACHE / seg / f"{d:%Y%m%d}.missing"
    if out.exists() or miss.exists():
        return seg, d, "cached"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url(seg, d), headers=HDR), timeout=30) as r:
                blob = r.read()
            if blob[:2] != b"PK":
                raise ValueError("not zip")
            out.write_bytes(blob)
            return seg, d, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                miss.write_text("404")
                return seg, d, "404"
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return seg, d, "fail"

def main(start, end):
    for s in ("cm", "fo"):
        (CACHE / s).mkdir(parents=True, exist_ok=True)
    # Weekdays plus known special weekend sessions (Budget / Muhurat days).
    special = {date(2025, 2, 1), date(2026, 2, 1), date(2026, 11, 8)}
    d, jobs = start, []
    while d <= end:
        if d.weekday() < 5 or d in special:
            jobs += [("cm", d), ("fo", d)]
        d += timedelta(days=1)
    stats = {}
    with ThreadPoolExecutor(3) as pool:
        for seg, day, status in pool.map(get, jobs):
            stats[status] = stats.get(status, 0) + 1
    print(stats)

if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]))
