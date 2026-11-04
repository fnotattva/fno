#!/usr/bin/env python3
"""Read-only NSE archive connectivity smoke test. No broker login, no orders."""
import csv
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nsearchives.nseindia.com/content"
DATES = ("20261030", "20261103")
SEGMENTS = ("FO", "CM")
MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}
results = {"utc_time": datetime.now(timezone.utc).isoformat(), "tests": []}

def open_request(opener, url, timeout=18):
    req = urllib.request.Request(url, headers=HEADERS)
    with opener.open(req, timeout=timeout) as response:
        final_url = response.geturl()
        if not urllib.parse.urlsplit(final_url).hostname.endswith(".nseindia.com"):
            raise ValueError("Redirected away from an NSE-controlled domain")
        content = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Archive too large for smoke test")
        return content, response.status, response.headers.get("Content-Type", ""), final_url

def inspect_zip(payload):
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError("Response is not a valid ZIP archive")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError("Corrupted ZIP entry: " + bad)
        names = [i for i in archive.namelist() if i.lower().endswith(".csv")]
        if not names:
            raise ValueError("ZIP does not contain any CSV files")
        entry = names[0]
        with archive.open(entry) as f:
            wrapper = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.reader(wrapper)
            headers = next(reader)
            sample = next(reader, [])
        if len(headers) < 5:
            raise ValueError("CSV unexpectedly has fewer than five columns")
        return {"entries": archive.namelist()[:6], "first_csv": entry, "csv_columns": headers[:50], "first_row_cells": len(sample)}

for date in DATES:
    for segment in SEGMENTS:
        filename = f"BhavCopy_NSE_{segment}_0_0_0_{date}_F_0000.csv.zip"
        url = f"{BASE}/{segment.lower()}/{filename}"
        item = {"date": date, "segment": segment, "url": url, "valid": False, "attempts": []}
        for mode in ("direct", "seeded_session"):
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            if mode == "seeded_session":
                try:
                    open_request(opener, "https://www.nseindia.com/", timeout=8)
                except Exception as exc:
                    item["attempts"].append({"mode": "seed", "error": f"{type(exc).__name__}: {str(exc)[:150]}"})
            try:
                data, status, media_type, final_url = open_request(opener, url)
                details = inspect_zip(data)
                item.update({"valid": True, "http_status": status, "content_type": media_type, "bytes": len(data),
                             "sha256": hashlib.sha256(data).hexdigest(), "resolved_url": final_url, "csv": details})
                item["attempts"].append({"mode": mode, "result": "valid zip and csv"})
                break
            except urllib.error.HTTPError as exc:
                item["attempts"].append({"mode": mode, "http_status": exc.code, "error": f"HTTP {exc.code}"})
            except Exception as exc:
                item["attempts"].append({"mode": mode, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})
        results["tests"].append(item)
        print(f"{segment} {date}: {'VALID ZIP' if item['valid'] else 'UNAVAILABLE'} | {item['attempts'][-1]}")
        time.sleep(1)

Path("probe_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
valid = [i for i in results["tests"] if i["valid"]]
print(f"VALID_ZIPS={len(valid)}/{len(results['tests'])}; saved probe_results.json")
if not valid:
    print("NSE DOWNLOAD BLOCKED ON GITHUB RUNNER — GitHub runner is not an exchange-approved data channel.")
