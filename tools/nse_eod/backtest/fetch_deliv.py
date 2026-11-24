"""Cache NSE sec_bhavdata_full (delivery %) for every cached CM session."""
import sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import store

OUT = store.CACHE / "deliv"; OUT.mkdir(parents=True, exist_ok=True)
HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}

def get(d):
    p = OUT / f"{d:%Y%m%d}.csv"
    if p.exists():
        return "cached"
    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
    for a in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=30) as r:
                b = r.read()
            if b[:6] != b"SYMBOL":
                raise ValueError("bad")
            p.write_bytes(b); return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "404"
            time.sleep(1.5 * (a + 1))
        except Exception:
            time.sleep(1.5 * (a + 1))
    return "fail"

with ThreadPoolExecutor(3) as pool:
    res = list(pool.map(get, store.days("cm")))
print({k: res.count(k) for k in set(res)})
