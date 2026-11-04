import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "nse_eod"))
from expert import expert_watch_candidate
from runner import render, track_prior


class ExpertOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.futures = {
            "SttlmPric":"102", "PrvsClsgPric":"101",
            "OpnIntrst":"30000","ChngInOpnIntrst":"-800",
            "TtlTradgVol":"550", "XpryDt":"2026-11-23"
        }
        self.tech = {
            "close":105,"open":101,"high":106,"low":100,
            "atr14":2,"cash_volume":2_000_000,"rvol20":1.8,
            "prev20_high":103,"prev20_low":85,"prev5_high":102,
            "prev5_low":95, "rsi14":76,
            "ema20":99,"ema50":97,"sma20":100,"sma50":96,"macd_hist":-0.3,
        }

    def test_breakout_may_be_watched_despite_failing_strict_oi_macd_and_rsi(self):
        idea = expert_watch_candidate("SAMPLE", self.futures, None,
                                      self.tech, date(2026,11,3))
        self.assertIsNotNone(idea)
        self.assertEqual(idea["directional_bias"],"LONG")
        self.assertTrue(idea["not_a_call"])
        self.assertIsNone(idea["recommendation"])
        self.assertIn("20-session cash breakout",idea["pattern"])
        self.assertIn("Futures regime not a fresh directional buildup",idea["caveats"])
        self.assertIn("MACD histogram not supportive",idea["caveats"])
        self.assertEqual(idea["data_quality"],"Verified NSE EOD cash and futures, options incomplete/unavailable")

    def test_low_liquidity_never_becomes_expert_pick(self):
        tech = {**self.tech,"cash_volume":100}
        self.assertIsNone(expert_watch_candidate("SAMPLE",self.futures,None,tech,date(2026,11,3)))

    def test_no_evidence_no_watchlist(self):
        tech = {**self.tech,"close":100,"open":100.4,"high":102,"low":99,
                "prev20_high":115,"prev20_low":80,"rvol20":1.01}
        self.assertIsNone(expert_watch_candidate("SAMPLE",self.futures,None,tech,date(2026,11,3)))

    def test_reversal_near_put_wall_without_full_trend_alignment(self):
        tech = {**self.tech, "close":99,"open":97,"high":100,"low":96,
                "atr14":3,"rvol20":1.3,"rsi14":40,
                "prev20_high":112, "prev20_low":84}
        chain = {"near_put_wall":97,"near_call_wall":113,"max_pain":105}
        idea = expert_watch_candidate("SAMPLE",self.futures,chain,tech,date(2026,11,3))
        self.assertIsNotNone(idea)
        self.assertIn("put-wall rejection",idea["pattern"])
        self.assertIsNone(idea["recommendation"])

    def test_separate_watchlist_and_no_strict_trade_is_explicit(self):
        idea=expert_watch_candidate("SAMPLE", self.futures, None, self.tech, date(2026,11,3))
        report=render({"market_date":"2026-11-03","requested_date":"2026-11-03",
                       "generated_ist":"2026-11-04T10:00:00+05:30",
                       "status":"VERIFIED EOD RESEARCH",
                       "candidates":[],"expert_opportunities":[idea],
                       "prior_updates":[]})
        self.assertIn("NO TRADE",report)
        self.assertIn("Expert Opportunities",report)
        self.assertIn("SAMPLE",report)
        self.assertIn("WATCH ONLY",report)
        self.assertIn("NOT trade calls",report)

    def test_same_day_repeat_does_not_fabricate_fills_or_exits(self):
        prior=[{"asof_date":"2026-11-04","signal":{
            "signal_id":"20261104-SAMPLE-LONG","symbol":"SAMPLE",
            "direction":"LONG","stop_loss":95,"entry_trigger":101,
            "target_1":110,"target_2":120}}]
        candle={"SAMPLE":{"HghPric":"125","LwPric":"90","ClsPric":"105"}}
        updates,kept=track_prior(prior,date(2026,11,4),candle)
        self.assertEqual(updates,[])
        self.assertEqual(kept,prior)

    def test_no_extra_names_when_none_pass(self):
        report=render({"market_date":"2026-11-03","requested_date":"2026-11-03",
                       "generated_ist":"2026-11-04T10:00:00+05:30",
                       "status":"VERIFIED EOD RESEARCH",
                       "candidates":[],"expert_opportunities":[],
                       "prior_updates":[]})
        self.assertIn("NO TRADE",report)
        self.assertIn("No additional credible ideas today",report)


if __name__ == "__main__":
    unittest.main()
