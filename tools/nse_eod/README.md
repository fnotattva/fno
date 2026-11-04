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
- Require at least 65 valid chronological CM sessions (the daily downloader requests up to 115 calendar days) to calculate **EMA20, EMA50, SMA20, SMA50, RSI14 (Wilder), MACD 12/26/9, recent EMA/SMA/MACD crosses, relative volume and ATR14**.
- Compute Fibonacci levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) from the previous **60 completed session** high/low, deliberately excluding today's candle to avoid lookahead. These are contextual support/resistance observations, not automatic reversal or target predictions.
- Mandatory technical confirmation: cash close and EMA20/SMA20 on the correct side of the trend, EMA20 vs EMA50 and SMA20 vs SMA50 alignment, rising/falling EMA20, RSI14 52–70 for longs or 30–48 for shorts, directional MACD signal/histogram, relative cash volume >=1.20x. Recent trend cross and five-session breakout strengthen the score. Reject overextended RSI or a contradictory signal even if futures OI is strong.
- Only **fresh futures LONG BUILDUP** qualifies for long recommendations and **fresh futures SHORT BUILDUP** for short recommendations, with >=2% same-contract OI change and >=0.5% futures daily price move. Short covering and long unwinding are diagnostics, **not standalone recommendations**.
- Independent score gates: futures >=35/40, options >=23/35, technicals >=23/25, aggregate >=85/100. Scores represent rule confluence and have NOT been calibrated to winning probabilities. A zero-pick day is valid and should simply say **NO TRADE**; never force a daily recommendation.
- Only produce conditional momentum WATCH research signals when fresh futures buildup, option-chain context, technical confluence, liquidity, structural levels, and risk rules pass together.
- Cash stock price defines entry/SL/targets. **Do not place a stock-futures trade at a cash-equity level**; futures trade levels require recalculation for basis and tick size.
- Initial SL uses day's range plus ATR buffer; T1 and T2 ~2.55R / 3.55R; modelled 0.15% of price round-trip cost is a scenario assumption, not actual charges. Net modelled T1 R:R must be >=2; risk <=4.5% and target distance <=11% of entry. Gap risk and slippage may make actual risk much higher.
- Intraday confirmation is not available from EOD files. Entry is contingent on next-session five-minute price confirmation *checked by the user/broker*, which the job cannot verify. No automatic executions or exit alerts.

## Two separate research outputs — no quota
**A. Strict high-conviction research opportunities** are unchanged. Up to 3 and often NONE, requiring the existing futures/option/technical score gates, usable risk and 2R+ net modelled targets. NEVER downgrade a failed strict candidate to an A-tier trade just to fill slots.

**B. Expert Opportunities — discretionary-style research watches** are a separate, optional list of up to 3 other stocks that could merit professional review despite failing *any number* of strict technical, OI or options filters. The engine explores independently observable NSE cash-price/volume breakouts or breakdowns, futures OI expansion near inflection levels, and reversal/rejection near relevant option walls. It can consider a stock even if its options chain is incomplete (disclosed). Each idea requires verifiable same-day NSE cash+futures EOD inputs, minimum cash turnover ~₹15 crore, futures OI/volume, historical-price coverage, a nontrivial volume and price-structure pattern, and a clear next-session decision level. Watch items disclose **why interesting**, **which strict filters remain unconfirmed/conflict**, **nearby options walls**, **price level requiring further confirmation**, and **whether an indicative stop is even sensible**. If no acceptable stop exists, explicitly state NOT TRADEABLE YET; do not invent SL/targets.

The secondary list is algorithmically generated and audited for patterns; it is **not equivalent to independent manual human/AI review of all company news**. An additional ChatGPT review may vet available verified corporate disclosures, market conditions and contradictory data before presentation, but must not invent catalysts or claim unseen events. Neither list is required to contain any stocks. A strict NO TRADE day may have 0–3 B-tier WATCH items; these are **not** substitutes for actionable top-tier recommendations. If nothing credible meets even the secondary evidence requirements, state no additional credible ideas.

## Schedule and delivery
- GitHub Actions workflow `.github/workflows/nse-eod-research.yml` runs at **13:45 UTC / 19:15 IST** on weekdays. GitHub Actions cron can be delayed, and NSE EOD files may not yet have published.
- If the latest day's FO or CM archive is inaccessible, the job writes `NO VERIFIED TRADE` instead of silently issuing a pick from a prior day. On a valid session when no candidate passes every filter, it writes **NO TRADE**, not a forced recommendation.
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
