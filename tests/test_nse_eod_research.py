import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "nse_eod"))
from logic import max_pain, chain_metrics, classify_futures, tech_metrics, research_candidate

class EODRulesTests(unittest.TestCase):
    def test_four_regimes(self):
        for p, oi, expected in [(1,2,"LONG BUILDUP"),(-1,2,"SHORT BUILDUP"),
                                (1,-2,"SHORT COVERING"),(-1,-2,"LONG UNWINDING"),
                                (0.01,2,"NEUTRAL"),(1,0.01,"NEUTRAL")]:
            self.assertEqual(classify_futures(p,oi),expected)

    def test_max_pain_hand_check(self):
        d = []
        ce = [10,20,120]
        pe = [40,100,10]
        for i,k in enumerate([90,100,110]):
            d += [{"StrkPric":str(k),"OptnTp":"CE","OpnIntrst":str(ce[i])},
                  {"StrkPric":str(k),"OptnTp":"PE","OpnIntrst":str(pe[i])}]
        # Small fixture is below the 12-strike completeness gate
        self.assertIsNone(max_pain(d))
        for k in range(20,32):
            d += [{"StrkPric":str(k),"OptnTp":"CE","OpnIntrst":"0"},
                  {"StrkPric":str(k),"OptnTp":"PE","OpnIntrst":"0"}]
        self.assertIsNone(max_pain(d))
        # Full liquid chain with uniform zero-impact extra strikes
        d = []
        for k in range(89,113):
            d += [{"StrkPric":str(k),"OptnTp":"CE","OpnIntrst":str(10 if k==90 else 20 if k==100 else 120 if k==110 else 1)},
                  {"StrkPric":str(k),"OptnTp":"PE","OpnIntrst":str(40 if k==90 else 100 if k==100 else 10 if k==110 else 1)}]
        pain = max_pain(d)
        self.assertGreaterEqual(pain["strike"], 95)
        self.assertLessEqual(pain["strike"], 105)

    def test_chain_walls_and_pcr(self):
        rows = []
        for k in range(80,105):
            rows += [
                {"StrkPric":str(k),"OptnTp":"CE","OpnIntrst":str(100 if k==101 else 4),"ChngInOpnIntrst":"2"},
                {"StrkPric":str(k),"OptnTp":"PE","OpnIntrst":str(140 if k==97 else 4),"ChngInOpnIntrst":"3"}]
        m = chain_metrics(rows, 99)
        self.assertEqual(m["call_wall"],101)
        self.assertEqual(m["put_wall"],97)
        self.assertGreater(m["pcr"],1)
        self.assertEqual(m["strike_count"],25)
        self.assertEqual(m["near_put_wall"],97)
        self.assertEqual(m["near_call_wall"],101)

    def test_trend_and_atr(self):
        history=[]
        for k in range(28):
            c=100+k
            history.append({"ClsPric":str(c),"HghPric":str(c+1),
                            "LwPric":str(c-1),"OpnPric":str(c-.5),
                            "TtlTradgVol":str(1000+k*15)})
        m=tech_metrics(history)
        self.assertGreater(m["ema20"],100)
        self.assertGreater(m["atr14"],0)
        self.assertLess(m["prev5_high"],float(history[-1]["HghPric"])+1)
        self.assertEqual(m["sessions"],28)

    def test_signal_requires_real_futures_oi(self):
        tech={"close":100,"atr14":2,"high":101,"low":99,"ema20":95,
              "prev5_high":99,"prev5_low":92,"open":99,
              "cash_volume":100000,"rvol20":1.8}
        chain={"near_put_wall":95,"near_call_wall":120,"max_pain":106,
               "previous_max_pain":105, "previous_pcr":1.1,
               "previous_put_wall":94,"previous_call_wall":120,"put_wall_shift":1,"call_wall_shift":0,
               "pcr":1.2,
               "pe_oi_change":3000,"ce_oi_change":-1000,
               "put_wall":95,"call_wall":120}
        fut={"SttlmPric":"101.5","PrvsClsgPric":"99.5","UndrlygPric":"100",
             "OpnIntrst":"300000","ChngInOpnIntrst":"20000",
             "TtlTradgVol":"1500","XpryDt":"2026-11-23"}
        c=research_candidate("DEMO",fut,chain,tech,date(2026,11,3))
        self.assertIsNotNone(c)
        self.assertEqual(c["direction"],"LONG")
        self.assertGreater(c["target_1"],c["entry_trigger"])
        self.assertLess(c["stop_loss"],c["entry_trigger"])
        self.assertGreaterEqual(c["modelled_net_rr_t1"],2)
        fut["OpnIntrst"]="0"
        self.assertIsNone(research_candidate("DEMO",fut,chain,tech,date(2026,11,3)))

if __name__=="__main__":
    unittest.main()
