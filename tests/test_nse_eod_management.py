"""Confirm the daily conditional lifecycle does not manufacture actual positions."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
from management import review_research_plans
from trade_plans import expert_trade_plan


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sig = {
            "signal_id":"20261111-DEMO-LONG-B-EXPERTPLAN","symbol":"DEMO",
            "direction":"LONG","market_date":"2026-11-11",
            "entry_trigger":106.0,"stop_loss":102.0,
            "target_1":110.0,"target_2":112.0,"target_3":114.0,
            "valid_for_next_sessions":2,"holding_max_sessions":5,
        }
        self.item = {"asof_date":"2026-11-11","last_checked":"2026-11-11",
                     "observed_sessions":0,"signal":self.sig}
        self.snap={
            "future":{"SttlmPric":"101","PrvsClsgPric":"100",
                      "OpnIntrst":"11000","ChngInOpnIntrst":"1000"},
            "chain":{"near_put_wall":95,"near_call_wall":115},
            "tech":{"atr14":2,"ema20":103,"prev5_low":100,"prev5_high":108,
                    "rsi14":60,"macd_hist":.4,"rvol20":1.4},
        }

    def review(self,item,day,hi=109,lo=106,close=107,snap=None):
        candle={"DEMO":{"HghPric":str(hi),"LwPric":str(lo),"ClsPric":str(close)}}
        updates,kept=review_research_plans([item],date.fromisoformat(day),candle,
                                            {"DEMO":snap or self.snap})
        return updates,kept

    def test_same_day_never_fabricates_entry(self):
        u,k=self.review(self.item,"2026-11-11")
        self.assertEqual(u,[])
        self.assertEqual(k,[self.item])

    def test_entry_touch_yields_conditional_not_verified_fill(self):
        u,k=self.review(self.item,"2026-11-12")
        self.assertEqual(len(k),1)
        self.assertFalse(u[0]["entry_confirmed"])
        self.assertFalse(u[0]["actual_position_known"])
        self.assertIn("UNVERIFIED",u[0]["status"])
        self.assertIn("IF CONFIRMED FILLED",u[0]["action_if_filled"])
        self.assertGreaterEqual(u[0]["suggested_stop_next_session_if_filled"],102)
        self.assertNotIn("realized",u[0]["fill_status"].lower())

    def test_two_sessions_without_touch_expires(self):
        u,k=self.review(self.item,"2026-11-12",hi=104,lo=103,close=103.5)
        self.assertEqual(len(k),1)
        u2,k2=self.review(k[0],"2026-11-13",hi=104,lo=103,close=103.5)
        self.assertIn("EXPIRED",u2[0]["status"])
        self.assertEqual(k2,[])

    def test_opposite_oi_plus_cash_weakness_suggests_exit(self):
        u,k=self.review(self.item,"2026-11-12")
        self.assertEqual(len(k),1)
        adverse={**self.snap,"future":{
            "SttlmPric":"99","PrvsClsgPric":"100",
            "OpnIntrst":"11000","ChngInOpnIntrst":"1000"
        },"tech":{**self.snap["tech"],"ema20":110,"macd_hist":-.5}}
        u,k=self.review(k[0],"2026-11-13",hi=108,lo=104,close=105,snap=adverse)
        self.assertIn("EXIT IF FILLED",u[0]["action_if_filled"])
        self.assertEqual(k,[])

    def test_stop_and_entry_same_day_sequence_remains_unknown(self):
        u,k=self.review(self.item,"2026-11-12",hi=113,lo=101,close=107)
        self.assertIn("ORDER UNKNOWN",u[0]["status"])
        self.assertEqual(k,[])

    def test_review_continues_after_five_and_terminates_at_t3(self):
        item=self.item
        dates=["2026-11-12","2026-11-13","2026-11-16","2026-11-17",
               "2026-11-18","2026-11-19","2026-11-20"]
        for d in dates:
            u,kept=self.review(item,d,hi=109,lo=106,close=107)
            self.assertEqual(len(kept),1)
            item=kept[0]
        self.assertEqual(u[0]["hypothetical_holding_sessions"],7)
        self.assertNotIn("TIME EXIT",u[0]["action_if_filled"])
        u,kept=self.review(item,"2026-11-23",hi=116,lo=106,close=115)
        self.assertIn("T3 PRICE LEVEL REACHED",u[0]["action_if_filled"])
        self.assertTrue(u[0]["terminal_for_scenario"])
        self.assertEqual(kept,[])

    def test_previous_suggested_trailing_stop_touch_ends_plan_not_faked_execution(self):
        updates,kept=self.review(self.item,"2026-11-12")
        self.assertEqual(len(kept),1)
        self.assertGreater(kept[0]["suggested_stop_if_filled"],102)
        updates,kept=self.review(kept[0],"2026-11-13",hi=109,lo=102.1,close=106)
        self.assertIn("TRAILING-STOP LEVEL TOUCHED",updates[0]["status"])
        self.assertIn("verify broker",updates[0]["action_if_filled"])
        self.assertEqual(kept,[])

    def test_missing_chain_prevents_updated_stop(self):
        u,kept=self.review(self.item,"2026-11-12",
                           snap={**self.snap,"chain":None})
        self.assertIn("REVIEW BLOCKED",u[0]["status"])
        self.assertEqual(len(kept),1)
        self.assertNotIn("suggested_stop_next_session_if_filled",u[0])

    def test_c_retest_risk_is_structural_not_fabricated_from_R(self):
        idea={"id":"20261111-DEMO-LONG-EXPERT","symbol":"DEMO",
              "directional_bias":"LONG","pattern_priority":4,
              "pattern":"20-session cash breakout with participation",
              "market_date":"2026-11-11","price_decision_level":106.1,
              "indicative_invalidation":None,"cash_close":105.5,
              "relative_volume":1.4,"futures_regime":"SHORT COVERING",
              "futures_change_pct":1.1,"futures_oi_change_pct":-2.0,
              "ema20":100,"ema50":99,"rsi14":67,"macd_hist":1.0,
              "put_wall":100,"call_wall":111,"max_pain":102,"caveats":[],
              "data_quality":"verified"}
        tech={"close":105.5,"atr14":2,"ema20":100,"rsi14":67,"macd_hist":1,
              "prev20_high":104,"prev5_high":103,"fib_swing_high60":115,
              "fib_swing_low60":85,"fib_levels60":{"0.786":108}}
        chain={"near_call_wall":111,"near_put_wall":100}
        self.assertIsNone(expert_trade_plan(idea,tech,chain,tier="B"))
        plan=expert_trade_plan(idea,tech,chain,tier="C")
        self.assertIsNotNone(plan)
        self.assertIn("pullback",plan["entry_pattern"])
        self.assertGreaterEqual(plan["modelled_net_rr_t1"],.60)
        self.assertGreater(plan["stop_loss"],0)
        self.assertLess(plan["stop_loss"],plan["entry_trigger"])
        self.assertIsNone(plan["holding_max_sessions"])
        self.assertIsNone(expert_trade_plan(idea,tech,None,tier="C"))


if __name__=="__main__":
    unittest.main()
