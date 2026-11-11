"""Official NSE dated CM OHLC and same-contract FO provenance regression checks."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
from evidence import (build_cash_paths, price_path_evidence, fetch_fo_evidence,
                      derivatives_evidence)
from management import review_research_plans


class HistoricalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.issued=date(2026,11,11)
        self.day1=date(2026,11,12)
        self.day2=date(2026,11,13)
        self.exp="2026-12-31"
        self.signal={"symbol":"DEMO","direction":"LONG",
                     "signal_id":"20261111-DEMO-LONG-EXPERTPLAN",
                     "market_date":self.issued.isoformat(),
                     "entry_trigger":106,"stop_loss":102,
                     "target_1":110,"target_2":112,"target_3":114}
        self.prior=[{"asof_date":self.issued.isoformat(),
                     "last_checked":self.issued.isoformat(),
                     "observed_sessions":0,"signal":self.signal}]
        self.today_cash=self._cash(108,109,106,107)
        self.hist={self.issued:[self._cash(105,106,103,105)],
                   self.day1:[self._cash(106,108,104,107)]}
        self.snapshots={"DEMO":{"future":{"FinInstrmTp":"STF",
                            "TckrSymb":"DEMO","XpryDt":self.exp,
                            "SttlmPric":"107","PrvsClsgPric":"105",
                            "OpnIntrst":"11000","ChngInOpnIntrst":"1000"},
                             "tech":{"ema20":104,"atr14":2,"prev5_low":101,
                                     "prev5_high":108,"rsi14":62,
                                     "macd_hist":1.0,"rvol20":1.4},
                             "chain":{"near_call_wall":115,
                                      "near_put_wall":100}}}

    def _cash(self,op,hi,lo,cl):
        return {"TckrSymb":"DEMO","SctySrs":"EQ",
                "OpnPric":str(op),"HghPric":str(hi),"LwPric":str(lo),
                "ClsPric":str(cl),"TtlTradgVol":"2000000"}

    def _fo(self, day, oi, prior_oi, settle, prev_settle):
        fut={"TradDt":day.isoformat(),"FinInstrmTp":"STF",
             "TckrSymb":"DEMO","XpryDt":self.exp,
             "SttlmPric":str(settle),"PrvsClsgPric":str(prev_settle),
             "OpnIntrst":str(oi),"ChngInOpnIntrst":str(oi-prior_oi),
             "TtlTradgVol":"500"}
        opts=[]
        for strike in range(90,151,5):
            for side in ("PE","CE"):
                opts.append({"TradDt":day.isoformat(),
                             "FinInstrmTp":"STO","TckrSymb":"DEMO",
                             "XpryDt":self.exp,"StrkPric":str(strike),
                             "OptnTp":side,"OpnIntrst":"1000",
                             "ChngInOpnIntrst":"100"})
        return [fut]+opts

    def test_dated_cash_trail_and_first_level_touches_are_not_fills(self):
        paths=build_cash_paths(self.hist,self.day2,[self.today_cash],
                               self.prior)
        self.assertEqual([p["date"] for p in paths["DEMO"]],
                         ["2026-11-11","2026-11-12","2026-11-13"])
        e=price_path_evidence(self.signal,paths["DEMO"])
        self.assertEqual(e["first_observed_entry_touch"],"2026-11-12")
        self.assertEqual(e["observed_sessions"],2)
        self.assertIsNone(e["level_first_touch_dates"]["T1"])
        self.assertFalse(e["entry_confirmed"])
        self.assertFalse(e["fills_known"])
        self.assertEqual(len(e["cm_archive_sources"]),2)
        self.assertTrue(all("BhavCopy_NSE_CM_" in x
                            for x in e["cm_archive_sources"]))
        self.assertIsNotNone(e["max_favourable_excursion_R_observed"])

    def test_same_day_stop_and_target_are_explicitly_ambiguous(self):
        path=[{"date":"2026-11-12","high":115,"low":101,"close":108,
               "open":106,"cash_volume":200000,
               "cm_source":"nse test"}]
        e=price_path_evidence(self.signal,path)
        self.assertEqual(e["entry_and_stop_same_day_ambiguity"],
                         ["2026-11-12"])
        self.assertEqual(e["level_first_touch_dates"]["T3"],"2026-11-12")
        self.assertFalse(e["intraday_sequence_known"])

    def test_futures_history_same_contract_OI_regimes_and_wall(self):
        a=self._fo(self.day1,9000,10000,103,105) # short buildup
        b=self._fo(self.day2,10000,9000,102,103) # short buildup
        paths=build_cash_paths(self.hist,self.day2,[self.today_cash],
                               self.prior)
        def loader(segment,day):
            self.assertEqual(segment,"FO")
            self.assertEqual(day,self.day1)
            return a
        trail,metadata=fetch_fo_evidence(
            self.prior,{self.day1:[self._cash(106,108,104,107)]},
            self.day2,b,self.snapshots,paths,loader=loader)
        self.assertEqual(metadata["historical_fo_downloaded"],1)
        self.assertEqual(metadata["historical_fo_requested"],1)
        data=derivatives_evidence(trail["DEMO"])
        self.assertEqual(data["status"],"VERIFIED FO HISTORY")
        self.assertEqual(data["days"],2)
        self.assertEqual(data["regimes"].get("SHORT BUILDUP"),2)
        self.assertTrue(all("BhavCopy_NSE_FO_" in row["fo_archive"]
                           for row in data["history"]))
        self.assertIsNotNone(data["latest_pcr"])
        self.assertEqual(data["same_contract_expiry"],self.exp)

    def test_missing_historical_FO_is_labeled_not_fabricated(self):
        paths=build_cash_paths(self.hist,self.day2,[self.today_cash],
                               self.prior)
        def loader(_segment,_day):
            from data import Unavailable
            raise Unavailable("NSE file unavailable")
        trail,metadata=fetch_fo_evidence(
            self.prior,{self.day1:[self._cash(106,108,104,107)]},
            self.day2,self._fo(self.day2,11000,10000,107,105),
            self.snapshots,paths,loader=loader)
        self.assertEqual(metadata["historical_fo_downloaded"],0)
        self.assertIn("2026-11-12",metadata["missing"])
        self.assertEqual(derivatives_evidence(trail["DEMO"])["days"],1)

    def test_rollover_is_not_mixed_into_new_contract_series(self):
        old=self._fo(self.day1,10000,9000,103,102)
        for row in old: row["XpryDt"]="2026-11-26"
        paths=build_cash_paths(self.hist,self.day2,[self.today_cash],
                               self.prior)
        trail,metadata=fetch_fo_evidence(
            self.prior,{self.day1:[self._cash(106,108,104,107)]},
            self.day2,self._fo(self.day2,11000,10000,107,105),
            self.snapshots,paths,loader=lambda _,__:old)
        self.assertEqual(trail["DEMO"][0]["status"],
                         "SAME-EXPIRY FUTURE MISSING")
        self.assertEqual(derivatives_evidence(trail["DEMO"])["days"],1)

    def test_two_verified_adverse_futures_days_affect_review(self):
        current=self.snapshots["DEMO"]
        # cash closes below entry but above old protective stop; MACD positive
        current["tech"].update({"ema20":100,"macd_hist":1.0})
        bars={"DEMO":self._cash(106,108,104,105)}
        previous={**self.prior[0],"observed_sessions":1,
                  "last_checked":"2026-11-12",
                  "first_entry_level_touch":"2026-11-12",
                  "suggested_stop_if_filled":102}
        path=[{"date":"2026-11-12","status":"VERIFIED NSE FO EOD",
               "futures_regime":"SHORT BUILDUP"},
              {"date":"2026-11-13","status":"VERIFIED NSE FO EOD",
               "futures_regime":"SHORT BUILDUP"}]
        updates,keep=review_research_plans(
            [previous],self.day2,bars,self.snapshots,
            derivatives_trails={"DEMO":path})
        self.assertTrue(updates[0]
                        ["two_verified_consecutive_adverse_futures_oi_days"])
        self.assertIn("TWO CONSECUTIVE",updates[0]["action_if_filled"])
        self.assertEqual(keep,[])

if __name__=="__main__":
    unittest.main()
