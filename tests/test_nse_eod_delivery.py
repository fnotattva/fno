import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "nse_eod"))
from runner import apply_coverage_status, render

class CoverageDeliveryTests(unittest.TestCase):
    def report(self, missing):
        return dict(status="VERIFIED EOD RESEARCH", coverage={"insufficient_cash_history": missing},
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
        data["candidates"] = [{"symbol": "EXAMPLE"}]
        apply_coverage_status(data)
        self.assertEqual(data["status"], "INCOMPLETE EOD RESEARCH")
        self.assertEqual(data["candidates"], [{"symbol": "EXAMPLE"}])

if __name__ == "__main__":
    unittest.main()
