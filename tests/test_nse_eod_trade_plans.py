"""B-tier conditional plan safety/structure/tracking regression checks."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
from trade_plans import expert_trade_plan, track_expert_plans
from runner import render


class ConditionalPlansTest(unittest.TestCase):
    def setUp(self):
        self.tech={
            "close":105.5, "high":106, "low":104,
            "atr14":2, "ema20":102, "ema50":100, "rsi14":62,
            "macd_hist":.4, "prev5_high":104, "prev20_high":104,
            "prev5_low":100, "prev20_low":95,
            "fib_swing_high60":112, "fib_swing_low60":88,
            "fib_levels60":{"0.618":109.3,"0.786":110.5},
        }
        self.idea={
            "id":"20261111-SAMPLE-LONG-EXPERT", "symbol":"SAMPLE",
            "directional_bias":"LONG", "pattern":"Price/volume breakout",
            "pattern_priority":4, "market_date":"2026-11-11",
            "cash_close":105.5, "relative_volume":2.2,
            "futures_regime":"LONG BUILDUP", "futures_change_pct":1.5,
            "futures_oi_change_pct":4.4,
            "ema20":102, "ema50":100, "rsi14":62, "macd_hist":.4,
            "price_decision_level":106.1, "indicative_invalidation":103.8,
            "put_wall":100, "call_wall":111, "max_pain":104,
            "caveats":["2R target beyond first wall"], "data_quality":"verified"
        }
        self.chain={"near_call_wall":111,"near_put_wall":100,"max_pain":104}

    def test_structure_based_t1_with_less_than_2r_is_permissible(self):
        p=expert_trade_plan(self.idea,self.tech,self.chain)
        self.assertIsNotNone(p)
        self.assertEqual(p["direction"],"LONG")
        self.assertGreater(p["target_1"],p["entry_trigger"])
        self.assertLess(p["target_1"],109.3)
        self.assertLess(p["stop_loss"],p["entry_trigger"])
        self.assertLess(p["modelled_net_rr_t1"],2)
        self.assertGreaterEqual(p["modelled_net_rr_t1"],.75)
        self.assertLess(p["target_1"],p["target_2"])
        self.assertLess(p["target_2"],p["target_3"])
        self.assertEqual(p["valid_for_next_sessions"],2)
        self.assertTrue(p["not_a_tier_a"])
        self.assertTrue(p["no_orders_placed"])
        self.assertIn("Fibonacci",p["target_sources"][0])
        report=render({"market_date":"2026-11-11","requested_date":"2026-11-11",
            "generated_ist":"2026-11-11T21:00:00+05:30",
            "status":"PARTIAL EOD RESEARCH","candidates":[],
            "expert_trade_plans":[p],"expert_opportunities":[],
            "prior_updates":[],"expert_prior_updates":[]})
        self.assertIn("CONDITIONAL CASH RESEARCH PLAN",report)
        self.assertIn("T3",report)
        self.assertIn("NO QUALIFYING B-TIER PLAN TODAY",render({
            "market_date":"2026-11-11","requested_date":"2026-11-11",
            "generated_ist":"2026-11-11T21:00:00+05:30","status":"PARTIAL EOD RESEARCH",
            "candidates":[],"expert_trade_plans":[],"expert_opportunities":[]}))

    def test_close_opposing_wall_blocks_weak_t1(self):
        c={**self.chain, "near_call_wall":106.4}
        self.assertIsNone(expert_trade_plan(self.idea,self.tech,c))

    def test_no_indicative_stop_no_trade_plan(self):
        self.assertIsNone(expert_trade_plan({**self.idea, "indicative_invalidation":None},self.tech,self.chain))
        self.assertIsNone(expert_trade_plan(self.idea,self.tech,None))
        self.assertIsNone(expert_trade_plan({**self.idea, "indicative_invalidation":100},self.tech,self.chain))

    def test_technical_and_futures_contradiction_remain_watch_only(self):
        self.assertIsNone(expert_trade_plan({**self.idea,"futures_regime":"SHORT BUILDUP"},self.tech,self.chain))
        self.assertIsNone(expert_trade_plan(self.idea,{**self.tech,"macd_hist":-.4},self.chain))
        self.assertIsNone(expert_trade_plan(self.idea,{**self.tech,"ema20":108},self.chain))
        self.assertIsNone(expert_trade_plan({**self.idea,"relative_volume":1.1},self.tech,self.chain))

    def test_short_structure_triggers_and_targets(self):
        t={**self.tech,"close":100,"ema20":104,"rsi14":38,"macd_hist":-.7,
           "prev5_low":95,"prev20_low":90,"fib_swing_low60":84,
           "fib_levels60":{"0.382":94.5,"0.236":88.0}}
        i={**self.idea,"directional_bias":"SHORT","id":"20261111-SAMPLE-SHORT-EXPERT",
           "futures_regime":"SHORT BUILDUP","cash_close":100,"ema20":104,
           "rsi14":38,"macd_hist":-.7,"price_decision_level":99,"indicative_invalidation":101,
           "put_wall":90,"call_wall":110}
        p=expert_trade_plan(i,t,{"near_put_wall":90,"near_call_wall":110})
        self.assertIsNotNone(p)
        self.assertLess(p["target_1"],p["entry_trigger"])
        self.assertLess(p["target_2"],p["target_1"])
        self.assertLess(p["target_3"],p["target_2"])

    def test_eod_tracking_never_invents_fill_and_expires_after_two_sessions(self):
        p=expert_trade_plan(self.idea,self.tech,self.chain)
        item={"asof_date":"2026-11-11","last_checked":"2026-11-11",
              "observed_sessions":0,"signal":p}
        candle={"SAMPLE":{"HghPric":"107","LwPric":"105","ClsPric":"106"}}
        updates,kept=track_expert_plans([item],date(2026,11,11),candle)
        self.assertEqual(updates,[])
        self.assertEqual(kept,[item])
        updates,kept=track_expert_plans([item],date(2026,11,12),candle)
        self.assertIn("5-MIN CONFIRMATION UNVERIFIED",updates[0]["status"])
        self.assertEqual(len(kept),1)
        updates2,kept2=track_expert_plans(kept,date(2026,11,12),candle)
        self.assertEqual(updates2,[])
        updates3,kept3=track_expert_plans(kept,date(2026,11,13),candle)
        self.assertEqual(updates3[0]["observed_sessions"],2)
        self.assertEqual(kept3,[])

    def test_simultaneous_stop_and_trigger_is_ambiguous(self):
        p=expert_trade_plan(self.idea,self.tech,self.chain)
        item={"asof_date":"2026-11-11","signal":p}
        row={"SAMPLE":{"HghPric":"112","LwPric":"103","ClsPric":"109"}}
        updates,_=track_expert_plans([item],date(2026,11,12),row)
        self.assertIn("ORDER/FILL UNKNOWN",updates[0]["status"])

if __name__=="__main__":
    unittest.main()
