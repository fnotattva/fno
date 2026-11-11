"""FnO Tattva user-facing trade idea quota: 2 ideal, 3 maximum TOTAL."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))

from shortlist import choose_daily_shortlist


class DailyShortlistTest(unittest.TestCase):
    def a(self,i):
        return {"symbol":f"A{i}","score":95}
    def b(self,i,rr=1.8,rvol=2.0,oi=4,regime="LONG BUILDUP"):
        return {"symbol":f"B{i}","modelled_net_rr_t1":rr,
                "cash_rvol20":rvol,"futures_oi_change_pct":oi,
                "futures_regime":regime}
    def c(self,i):
        return {"symbol":f"C{i}","modelled_net_rr_t1":0.7}

    def test_zero_qualifiers_never_forced(self):
        a,b,c,p=choose_daily_shortlist([],[],[])
        self.assertEqual((a,b,c),([],[],[]))
        self.assertEqual(p["fresh_conditional_ideas"],0)

    def test_default_two_even_if_many_c(self):
        a,b,c,p=choose_daily_shortlist([],[],[self.c(i) for i in range(8)])
        self.assertEqual(len(c),2)
        self.assertEqual(p["fresh_conditional_ideas"],2)
        self.assertEqual(p["not_selected"],6)

    def test_a_tier_preferred_and_three_if_exceptional(self):
        a,b,c,p=choose_daily_shortlist([self.a(1),self.a(2),self.a(3)],
                                        [self.b(1)], [self.c(1)])
        self.assertEqual(len(a),3)
        self.assertEqual(len(b),0)
        self.assertEqual(len(c),0)
        self.assertEqual(p["fresh_conditional_ideas"],3)

    def test_third_b_requires_minimum_evidence(self):
        a,b,c,p=choose_daily_shortlist([self.a(1)],[
            self.b(1),self.b(2,rr=1.4)],[])
        self.assertEqual((len(a),len(b),len(c)),(1,1,0))
        self.assertEqual(p["fresh_conditional_ideas"],2)
        a,b,c,p=choose_daily_shortlist([self.a(1)],[
            self.b(1),self.b(2,rr=1.7)],[])
        self.assertEqual((len(a),len(b),len(c)),(1,2,0))
        self.assertEqual(p["fresh_conditional_ideas"],3)

    def test_ongoing_research_is_not_a_filled_broker_position(self):
        active=[{"signal":{"symbol":"B1"}}]
        a,b,c,p=choose_daily_shortlist([self.a(1)],
            [self.b(1),self.b(2),self.b(3)],[],active_research=active)
        self.assertEqual(len(a)+len(b)+len(c),3)
        self.assertTrue(all(x["symbol"]!="B1" for x in a+b+c))
        self.assertEqual(p["prior_research_ideas_under_review"],1)
        self.assertEqual(p["verified_open_positions_count"],0)

    def test_verified_positions_reduce_capacity_if_provided(self):
        a,b,c,p=choose_daily_shortlist([self.a(1),self.a(2),self.a(3)],
            [],[],verified_open_positions=["OWN1","OWN2"])
        self.assertEqual(len(a),1)
        self.assertEqual(p["fresh_research_slots"],1)
        a,b,c,p=choose_daily_shortlist([self.a(1)],[],[],
            verified_open_positions=["OWN1","OWN2","OWN3"])
        self.assertEqual((a,b,c),([],[],[]))
        self.assertEqual(p["fresh_research_slots"],0)

    def test_duplicate_symbol_and_cannot_raise_tier(self):
        a,b,c,p=choose_daily_shortlist([{"symbol":"DUP"}],
            [{"symbol":"DUP"},self.b(2)],
            [{"symbol":"DUP"},self.c(1)])
        self.assertEqual([x["symbol"] for x in a+b+c],["DUP","B2"])

    def test_no_more_than_three_over_any_mix(self):
        a,b,c,p=choose_daily_shortlist([self.a(1)],
            [self.b(i) for i in range(30)],
            [self.c(i) for i in range(30)])
        self.assertLessEqual(len(a)+len(b)+len(c),3)
        self.assertEqual(p["daily_fresh_cap"],3)


if __name__=="__main__":
    unittest.main()
