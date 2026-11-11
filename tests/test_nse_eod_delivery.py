import json
import tempfile
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "nse_eod"))
from data import Unavailable, cash_history, market_closure, most_recent
from runner import apply_coverage_status, render, main

class CoverageDeliveryTests(unittest.TestCase):
    def report(self, missing):
        return dict(status="VERIFIED EOD RESEARCH", coverage={"insufficient_cash_history": missing,
                                                               "valid_history_and_chain": 0},
                    errors=[], market_date="2026-11-06", requested_date="2026-11-06",
                    generated_ist="2026-11-06T21:15:59+05:30", candidates=[], expert_opportunities=[])
    def test_missing_history_is_not_verified_no_trade(self):
        data = self.report(218)
        apply_coverage_status(data)
        text = render(data)
        self.assertEqual(data["status"], "INCOMPLETE EOD RESEARCH")
        self.assertIn("218 stocks", text)
        self.assertNotIn("**NO TRADE.**", text)
        self.assertNotIn("No additional credible ideas today", text)
    def test_complete_zero_pick_day_remains_valid(self):
        data = self.report(0)
        apply_coverage_status(data)
        self.assertEqual(data["status"], "VERIFIED EOD RESEARCH")
        self.assertIn("**NO TRADE.**", render(data))
    def test_partial_history_discloses_coverage_without_changing_picks(self):
        data = self.report(1)
        data["coverage"]["valid_history_and_chain"] = 217
        data["candidates"] = [{"symbol": "EXAMPLE"}]
        apply_coverage_status(data)
        self.assertEqual(data["status"], "PARTIAL EOD RESEARCH")
        self.assertEqual(data["candidates"], [{"symbol": "EXAMPLE"}])

    def test_history_fetches_in_batches_until_minimum_is_met(self):
        calls = []
        def fake_load(segment, day):
            calls.append(day)
            if day == date(2026, 11, 4):
                raise Unavailable("holiday")
            return [{"TradDt": day.isoformat()}]
        with patch("data.load", side_effect=fake_load):
            history, errors = cash_history(
                date(2026, 11, 6), days=20, workers=2,
                minimum_sessions=4, batch_size=3,
            )
        self.assertGreaterEqual(len(history), 4)
        self.assertIn("2026-11-04", errors)
        self.assertLessEqual(len(calls), 6)


    def test_official_diwali_holiday_calendar(self):
        self.assertEqual(market_closure(date(2026, 11, 10)), "Diwali-Balipratipada")
        self.assertIsNone(market_closure(date(2026, 11, 11)))
        self.assertIsNotNone(market_closure(date(2026, 11, 8)))

    def test_holiday_report_never_downloads_or_issues_picks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("runner.OUTPUT", Path(tmp) / "out"), \
                 patch("runner.most_recent") as archive_fetch, \
                 patch("sys.argv", ["runner.py", "--asof", "2026-11-10"]):
                self.assertEqual(main(), 0)
                archive_fetch.assert_not_called()
            result = json.loads((Path(tmp) / "out" / "report.json").read_text())
            text = (Path(tmp) / "out" / "report.md").read_text()
            self.assertEqual(result["status"], "MARKET HOLIDAY")
            self.assertEqual(result["requested_date"], "2026-11-10")
            self.assertIsNone(result["market_date"])
            self.assertEqual(result["candidates"], [])
            self.assertEqual(result["expert_opportunities"], [])
            self.assertIn("MARKET HOLIDAY — NO EOD SCAN REQUIRED", text)
            self.assertNotIn("**NO TRADE.**", text)

    def test_archive_lookback_and_history_skip_official_holiday(self):
        with patch("data.load", return_value=[{"TradDt": "2026-11-09"}]) as fetch:
            last_date, _, _, _ = most_recent(date(2026, 11, 10))
            self.assertEqual(last_date, date(2026, 11, 9))
            self.assertTrue(all(call.args[1] != date(2026, 11, 10) for call in fetch.call_args_list))
        with patch("data.load", return_value=[{"TradDt": "2026-11-09"}]) as fetch:
            history, errors = cash_history(
                date(2026, 11, 11), days=3, workers=1,
                minimum_sessions=1, batch_size=3,
            )
            self.assertIn(date(2026, 11, 9), history)
            self.assertNotIn("2026-11-10", errors)
            self.assertTrue(all(call.args[1] != date(2026, 11, 10) for call in fetch.call_args_list))

if __name__ == "__main__":
    unittest.main()


