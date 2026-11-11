# NSE EOD artifact delivery
Use the connected GitHub fetch tool with:
https://api.github.com/repos/fnotattva/fno/actions/workflows/nse-eod-research.yml/runs?branch=main&per_page=30

Paginate if necessary. Include push, schedule and workflow_dispatch runs.
Do not use fetch_commit_workflow_runs to find a heartbeat: that wrapper filters to pull-request events and can return an empty result for a successful push.

Before any recovery trigger, inspect queued, in-progress and completed runs for the market session and heartbeat SHA. Reuse the existing run; do not duplicate it.
For a completed successful run, list artifacts, download nse-eod-research-report, verify the ZIP SHA256 against GitHub's digest, and extract report.json and report.md.

Validate requested_date, market_date, generation timestamp, source archive URLs, errors, history_sessions and per-stock coverage. Workflow success alone is not research completeness. Empty A/B lists with insufficient history are inconclusive. Never substitute an old replay or offline test output.

## 6 November 2026 incident
Heartbeat fb656e71ca63d2702f7b09007c4be2d9d5038f7d produced successful run 42246064023, completed 15:47:30 UTC (21:17:30 IST).
Artifact 13518985730 ZIP SHA256:
4280abf94956ab23a5c5c59f91c8145d3ca10bfe299b8bf5757273bda19b7167

The artifact requested and reported market date 2026-11-06. It contained 218 futures and 218 valid chains, but only 47 prior history sessions and 36 unavailable weekday archives. All 218 stocks failed technical-history coverage. The original VERIFIED EOD RESEARCH label and no-trade prose therefore overstate completeness. There are no validated A/B picks, and no valid market-wide no-trade conclusion.

The incident was caused by an unbounded burst of eight parallel history requests with no retry path. Official archive spot checks across July-November succeeded, and a local reproduction recovered 80 prior sessions; the three unavailable weekday dates were exchange holidays. The repair uses three workers, small batches, bounded retry/backoff for transient HTTP responses, and stops after enough clean sessions for the 65-session technical minimum.\n\nThe reporting patch marks zero technical coverage INCOMPLETE EOD RESEARCH, distinguishes partial coverage, and preserves per-date download errors. It changes no scoring thresholds, paid services, credentials or order behavior.


## 10 November 2026: confirmed NSE holiday, not an archive outage

NSE/CMTR/71775 (cash) and NSE/FAOP/71777 (F&O) designate Tuesday
2026-11-10 as **Diwali-Balipratipada**, a full regular-trading holiday.
A missing 10 November FO/CM bhavcopy is expected and must never be
reported as an NSE download failure or treated as an incomplete trading-day scan.

The runner now checks the official 2026 NSE calendar before any archive
request. On a listed closure it emits `status: MARKET HOLIDAY`,
`market_date: null`, `holiday_reason`, empty A/B lists, and an explicit
"No EOD scan required" explanation. It does not fetch stale prior-day
archives or trigger recovery. Historical lookbacks skip exchange holidays
without counting their expected absence as HTTP 404 errors.

The 2026 holiday calendar is intentionally explicit; update it from NSE's
official circular/calendar before relying on subsequent calendar years.
The weekend special Muhurat session is not a normal weekday EOD scan.

Sources:
- https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf
- https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf

For Wednesday 2026-11-11, wait for verified current-session NSE FO/CM
archives after the close; do not use 9 November prices as 11 November data.
