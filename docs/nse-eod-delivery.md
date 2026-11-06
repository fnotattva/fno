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

The reporting patch marks missing technical-history coverage INCOMPLETE EOD RESEARCH and preserves per-day history download errors. It changes no scoring, thresholds, archive requests, paid services, credentials or order behavior. Historical download failures cannot be diagnosed retrospectively from the original artifact because it retained only their count.
