import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "nse_eod"))
from logic import max_pain, chain_metrics, classify_futures, tech_metrics, research_candidate, wall_premium_proxy
from technicals import ema_series, sma_series, wilder_rsi, macd_series, technical_confirmation

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

    def test_full_chain_payout_vs_bruteforce(self):
        rows = []
        strikes = list(range(80, 121, 2))
        for k in strikes:
            rows.extend([
                {"StrkPric":str(k),"OptnTp":"CE","OpnIntrst":str((k*17)%97 + 2),"ChngInOpnIntrst":"1"},
                {"StrkPric":str(k),"OptnTp":"PE","OpnIntrst":str((k*23)%89 + 2),"ChngInOpnIntrst":"1"}])
        computed = max_pain(rows)
        self.assertIsNotNone(computed)
        brute = {settle:sum(max(settle-float(r["StrkPric"]),0)*float(r["OpnIntrst"])
                       if r["OptnTp"]=="CE" else
                       max(float(r["StrkPric"])-settle,0)*float(r["OpnIntrst"])
                       for r in rows) for settle in strikes}
        expected = min(strikes,key=lambda settle:brute[settle])
        self.assertEqual(computed["strike"], expected)
        self.assertAlmostEqual(computed["payout_price_units"], brute[expected], places=3)

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

    def test_writing_proxies_are_explicitly_inferred(self):
        rows = [
            {"StrkPric":"100","OptnTp":"CE","OpnIntrst":"500","ChngInOpnIntrst":"100",
             "ClsPric":"2.0","PrvsClsgPric":"3.0","TtlTradgVol":"100"},
            {"StrkPric":"90","OptnTp":"PE","OpnIntrst":"400","ChngInOpnIntrst":"-100",
             "ClsPric":"4.0","PrvsClsgPric":"3.0","TtlTradgVol":"120"}]
        self.assertEqual(wall_premium_proxy(rows, 100, "CE")["label"],"WRITING-LIKE")
        self.assertEqual(wall_premium_proxy(rows, 90, "PE")["label"],"UNWINDING/COVERING-LIKE")

    def test_trend_and_atr(self):
        history=[]
        for k in range(75):
            c=100+k
            history.append({"ClsPric":str(c),"HghPric":str(c+1),
                            "LwPric":str(c-1),"OpnPric":str(c-.5),
                            "TtlTradgVol":str(1000+k*15)})
        m=tech_metrics(history)
        self.assertGreater(m["ema20"],100)
        self.assertGreater(m["atr14"],0)
        self.assertLess(m["prev5_high"],float(history[-1]["HghPric"])+1)
        self.assertEqual(m["sessions"],75)
        self.assertIsNotNone(m["ema50"])
        self.assertIsNotNone(m["sma50"])
        self.assertGreater(m["rsi14"],0)
        self.assertEqual(len(m["fib_levels60"]),7)

    def test_indicators_use_completed_history_only(self):
        rising = [100 + i*0.4 + (i % 3)*0.1 for i in range(75)]
        self.assertEqual(len(ema_series(rising,50)),75)
        self.assertEqual(sma_series([1,2,3,4],3),[None,None,2.0,3.0])
        self.assertGreater(wilder_rsi(rising)[-1],70)
        macd, signal, hist = macd_series(rising)
        self.assertIsNotNone(hist[-1])
        self.assertIsNotNone(signal[-1])
        self.assertIsNotNone(macd[-1])

    def test_technical_rejects_mixed_or_exhausted(self):
        template={"close":100,"ema20":95,"ema50":90,"sma20":96,"sma50":92,
                  "ema20_prev":94,"rsi14":59,"macd":1.3,"macd_signal":0.7,
                  "macd_hist":0.6,"rvol20":1.6,"prev5_high":99,
                  "prev5_low":89,"ema_crossover":None}
        self.assertTrue(technical_confirmation(template,"LONG")["approved"])
        self.assertFalse(technical_confirmation({**template,"rsi14":79},"LONG")["approved"])
        self.assertFalse(technical_confirmation({**template,"ema20":88},"LONG")["approved"])
        self.assertFalse(technical_confirmation({**template,"macd_hist":-0.2},"LONG")["approved"])
        self.assertFalse(technical_confirmation({**template,"rvol20":0.5},"LONG")["approved"])

    def test_short_covering_does_not_become_top_tier_recommendation(self):
        tech={"close":100,"atr14":2,"high":101,"low":99,"ema20":95,
              "ema50":90,"sma20":96,"sma50":92,"ema20_prev":94,
              "rsi14":59,"macd":1.3,"macd_signal":0.7,"macd_hist":0.6,
              "rvol20":1.6,"prev5_high":99,"prev5_low":90,
              "ema_crossover":{"direction":"BULLISH","sessions_ago":1},
              "sma_crossover":None,"fib_swing_high60":108,"fib_swing_low60":80,
              "fib_support":98,"fib_resistance":101,"fib_levels60":{"0.5":94},
              "open":99,"cash_volume":200000}
        chain={"near_put_wall":96,"near_call_wall":122,"max_pain":105,
               "previous_max_pain":104,"previous_pcr":1.0,
               "previous_put_wall":95,"previous_call_wall":122,
               "put_wall_shift":1,"call_wall_shift":0,"pcr":1.15,
               "pe_oi_change":3000,"ce_oi_change":-2000,
               "put_wall":96,"call_wall":122,
               "put_wall_premium_proxy":{"label":"WRITING-LIKE","oi_change":500},
               "call_wall_premium_proxy":{"label":"MIXED","oi_change":0}}
        future={"SttlmPric":"101.5","PrvsClsgPric":"99.5","UndrlygPric":"100",
                "OpnIntrst":"280000","ChngInOpnIntrst":"-20000",
                "TtlTradgVol":"2000","XpryDt":"2026-11-23"}
        self.assertIsNone(research_candidate("DEMO",future,chain,tech,date(2026,11,3)))

    def test_signal_requires_real_futures_oi(self):
        tech={"close":100,"atr14":2,"high":101,"low":99,"ema20":95,
              "ema50":90, "sma20":96, "sma50":92, "ema20_prev":94,
              "rsi14":58, "macd":1.5, "macd_signal":1.0, "macd_hist":0.5,
              "ema_crossover":{"direction":"BULLISH","sessions_ago":2},
              "sma_crossover":None, "fib_swing_high60":103,
              "fib_swing_low60":85, "fib_support":98, "fib_resistance":101,
              "fib_levels60":{"0.5":94,"0.618":96.12},
              "prev5_high":99,"prev5_low":92,"open":99,
              "cash_volume":100000,"rvol20":1.8}
        chain={"near_put_wall":95,"near_call_wall":120,"max_pain":106,
               "previous_max_pain":105, "previous_pcr":1.1,
               "previous_put_wall":94,"previous_call_wall":120,"put_wall_shift":1,"call_wall_shift":0,
               "put_wall_premium_proxy":{"label":"MIXED","oi_change":0,"premium_pct":None},
               "call_wall_premium_proxy":{"label":"MIXED","oi_change":0,"premium_pct":None},
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
