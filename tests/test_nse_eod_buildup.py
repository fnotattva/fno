"""Futures buildup research: eligibility, no forced trades, no invented fills."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
from runner import buildup_watch_candidate
from trade_plans import expert_trade_plan

def tech():
    return {"close":112,"open":108,"high":113,"low":109,"atr14":5,
            "ema20":105,"ema50":102,"macd_hist":2,"rsi14":65,
            "cash_volume":2000000,"rvol20":2.5,
            "prev5_high":111,"prev5_low":98,
            "prev20_high":114,"prev20_low":95,
            "fib_swing_high60":130,"fib_swing_low60":90,"fib_levels60":{}}
def future():
    return {"SttlmPric":112,"PrvsClsgPric":109,"OpnIntrst":110000,
            "ChngInOpnIntrst":10000,"TtlTradgVol":500}
def chain():
    return {"near_put_wall":100,"near_call_wall":120,"max_pain":110}

class FuturesBuildupTests(unittest.TestCase):
    def test_eligible_buildup_stays_conditional(self):
        x=buildup_watch_candidate("EXAMPLE",future(),chain(),tech(),date(2026,11,12))
        self.assertIsNotNone(x)
        self.assertEqual(x["directional_bias"],"LONG")
        self.assertEqual(x["pattern_priority"],4)
        p=expert_trade_plan(x,tech(),chain(),future(),tier="C")
        if p:
            self.assertTrue(p["no_orders_placed"])
            self.assertGreaterEqual(p["modelled_net_rr_t1"],.6)
            self.assertLessEqual(p["initial_risk_pct"],4.5)
    def test_no_fresh_oi(self):
        f=future();f["ChngInOpnIntrst"]=-10000
        self.assertIsNone(buildup_watch_candidate("EXAMPLE",f,chain(),tech(),date(2026,11,12)))
    def test_missing_chain_or_volume(self):
        self.assertIsNone(buildup_watch_candidate("EXAMPLE",future(),None,tech(),date(2026,11,12)))
        t=tech();t["rvol20"]=1.1
        self.assertIsNone(buildup_watch_candidate("EXAMPLE",future(),chain(),t,date(2026,11,12)))
    def test_conflicting_momentum(self):
        t=tech();t["macd_hist"]=-2
        self.assertIsNone(buildup_watch_candidate("EXAMPLE",future(),chain(),t,date(2026,11,12)))

if __name__=="__main__":
    unittest.main()
