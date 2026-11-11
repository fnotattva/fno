"""User preference: 2 normal, BUT no hard cap for exceptional A/B/C ideas."""
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
    def c(self,i,rr=0.7,rvol=1.5,oi=0.8,regime="SHORT COVERING",priority=4):
        return {"symbol":f"C{i}","modelled_net_rr_t1":rr,
                "cash_rvol20":rvol,"futures_oi_change_pct":oi,
                "futures_regime":regime,"pattern_priority":priority}

    def test_zero_qualifiers_never_forced(self):
        a,b,c,p=choose_daily_shortlist([],[],[])
        self.assertEqual((a,b,c),([],[],[]))
        self.assertEqual(p["fresh_conditional_ideas"],0)
        self.assertIsNone(p["hard_daily_cap"])

    def test_normal_two_even_if_many_nonexceptional_c(self):
        a,b,c,p=choose_daily_shortlist([],[],[self.c(i) for i in range(8)])
        self.assertEqual(len(c),2)
        self.assertEqual(p["fresh_conditional_ideas"],2)
        self.assertEqual(p["not_selected"],6)

    def test_four_strict_a_ideas_not_capped_at_three(self):
        a,b,c,p=choose_daily_shortlist([self.a(i) for i in range(5)],
                                        [self.b(1)], [self.c(1)])
        self.assertEqual(len(a),5)
        self.assertEqual(len(b),1)
        self.assertEqual(len(c),0)
        self.assertEqual(p["fresh_conditional_ideas"],6)
        self.assertEqual(p["exceptional_ideas_beyond_normal"],4)

    def test_all_exceptional_b_are_included_beyond_three(self):
        a,b,c,p=choose_daily_shortlist([],[
            self.b(1),self.b(2),self.b(3),self.b(4),self.b(5)],[])
        self.assertEqual(len(b),5)
        self.assertEqual(p["fresh_conditional_ideas"],5)

    def test_extra_nonexceptional_b_rejected_but_later_excellent_passes(self):
        a,b,c,p=choose_daily_shortlist([self.a(1)],[
            self.b(1),self.b(2,rr=1.4),self.b(3,rr=1.9)],[])
        self.assertEqual([x["symbol"] for x in a+b+c],["A1","B1","B3"])
        self.assertEqual(p["not_selected"],1)

    def test_additional_c_requires_even_higher_evidence(self):
        a,b,c,p=choose_daily_shortlist([],[],
            [self.c(1),self.c(2),
             self.c(3,rr=2.3,rvol=2.5,oi=4,regime="SHORT BUILDUP")])
        self.assertEqual([x["symbol"] for x in c],["C1","C2","C3"])
        self.assertEqual(p["fresh_conditional_ideas"],3)

    def test_ongoing_old_research_does_not_block_fresh(self):
        active=[{"signal":{"symbol":"B1"}}]
        a,b,c,p=choose_daily_shortlist([self.a(1)],
            [self.b(1),self.b(2),self.b(3),self.b(4)],[],
            active_research=active)
        self.assertEqual([x["symbol"] for x in a+b+c],["A1","B2","B3","B4"])
        self.assertEqual(p["prior_research_ideas_under_review"],1)

    def test_actual_holdings_are_disclosed_not_used_to_hide_research(self):
        a,b,c,p=choose_daily_shortlist([self.a(i) for i in range(5)],
            [],[],verified_open_positions=["OWN1","OWN2","OWN3"])
        self.assertEqual(len(a),5)
        self.assertEqual(p["verified_open_positions_count"],3)
        self.assertIn("DO NOT cap",p["note"])

    def test_duplicate_symbols_not_relisted_in_two_tiers(self):
        a,b,c,p=choose_daily_shortlist([{"symbol":"DUP"}],
            [{"symbol":"DUP"},self.b(2)],
            [{"symbol":"DUP"},self.c(1)])
        self.assertEqual([x["symbol"] for x in a+b+c],["DUP","B2"])

    def test_no_extra_weak_calls_ever_forced(self):
        a,b,c,p=choose_daily_shortlist([self.a(1),self.a(2)],
            [self.b(i,rr=0.8,oi=0.7,rvol=1.2) for i in range(1,20)],
            [self.c(i) for i in range(20)])
        self.assertEqual(len(a)+len(b)+len(c),2)
        self.assertGreater(p["not_selected"],20)


if __name__=="__main__":
    unittest.main()
