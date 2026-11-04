# FnO Tattva NSE EOD Futures + Options OI Radar

**Research-only, ₹0, NSE official end-of-day data, no broker/API login, no intraday monitor, no real orders.**

## Validated inputs
- NSE F&O UDiFF Common Bhavcopy Final: `BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip`.
- NSE CM UDiFF Common Bhavcopy: `BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`.
- Workflow uses a ZIP-capable GitHub-hosted Python runner, so a chat web-reader's inability to open `application/zip` is irrelevant.
- Validates each ZIP, CSV field schema, trade date, existence of stock futures (`STF`) and stock options (`STO`), same underlying/expiry coverage, historical CM OHLCV consistency.
- Runner and tests use only Python standard library and GitHub Actions' free public-repository runners.

## Calculations
- Select the nearest non-expired `STF` contract for each stock; ignore expiry/roll window (<=3 calendar days).
- Classify futures settlement movement vs previous settlement and same-contract daily OI movement into long buildup / short buildup / short covering / long unwinding. This is *not* proof of which side initiated the trading.
- Use a complete available `STO` strike list for the same underlying and futures expiry. Identify highest-PE-OI put wall, highest-CE-OI call wall, relevant nearby walls, PCR and max pain (minimum intrinsic settlement payout across all listed strikes).
- Calculate OI changes directly from exchange `ChngInOpnIntrst`, with aggregate put/call OI change for context; not proof of option writing or unwinding transactions.
- Use 22+ recent actual CM sessions for EMA20, ATR14, relative volume and five-day highs/lows. EMA50, when at least 50 sessions are available, is optional; no EMA50 assertion otherwise.
- Only produce conditional momentum WATCH research signals when price/futures regime, liquidity, risk, OI wall clearance and evidence score align.
- Cash stock price defines entry/SL/targets. **Do not place a stock-futures trade at a cash-equity level**; futures trade levels require recalculation for basis and tick size.
- Initial SL uses day's range plus ATR buffer; T1 and T2 ~2.55R / 3.55R; modelled 0.15% of price round-trip cost is a scenario assumption, not actual charges. Net modelled T1 R:R must be >=2; risk <=4.5% and target distance <=11% of entry. Gap risk and slippage may make actual risk much higher.
- Intraday confirmation is not available from EOD files. Entry is contingent on next-session five-minute price confirmation *checked by the user/broker*, which the job cannot verify. No automatic executions or exit alerts.

## Schedule and delivery
- GitHub Actions workflow `.github/workflows/nse-eod-research.yml` runs at **13:45 UTC / 19:15 IST** on weekdays. GitHub Actions cron can be delayed, and NSE EOD files may not yet have published.
- If the latest day's FO or CM archive is inaccessible, the job writes `NO VERIFIED TRADE` instead of silently issuing a pick from a prior day.
- Workflow creates **Actions artifacts** `nse-eod-research-report` containing `report.md` and `report.json`, retained for 14 days. This workflow does not publish picks to the application's code or commit them to the public repository.
- Stores a limited research watchlist state through GitHub Actions cache (best effort; cache may expire). It never knows which actual positions were traded.
- Separate ChatGPT EOD notification should run **after** this workflow and retrieve the latest successful report artifact using the connected GitHub tool. The GitHub Actions service and the ChatGPT scheduled task are separate processes. A passing download is not proof that the ChatGPT task retrieved the report.

## Testing
`python -m unittest discover -s tests -p 'test_nse_eod_research.py' -v`
`python tools/nse_eod/runner.py --asof 2026-11-03` (historical reproducibility; uses live official archived downloads)

**Important:** Strictly educational/research; does not promise accuracy, guarantee stops/targets, or execute trades. Any distribution as research recommendations should undergo SEBI RA and exchange/data licensing compliance review.

## Security
- No API keys, no tokens, no paid connection, no passwords.
- NSE HTTPS host validation, download and ZIP decompression size caps, data/date/schema checks, limited workflow permissions (`contents: read`).
- Github workflows cannot safely guarantee downloads forever. Failed/incomplete exchange files trigger NO VERIFIED TRADE.
