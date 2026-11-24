"""Evidence-calibrated quality gate, T1 cap, corporate actions, special sessions."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
from quality import (quality_gate, demote_to_watch, market_context, market_breadth,
                     trend_maturity_atr, MIN_RVOL, T1_CAP_R)
from technicals import adjust_corporate_actions, compute_technicals
from trade_plans import expert_trade_plan
from data import market_closure, history_session, NSE_SPECIAL_SESSIONS_2026
from runner import render, analysis_contract


def bar(o, h, l, c, v=1000):
    return {"OpnPric": str(o), "HghPric": str(h), "LwPric": str(l), "ClsPric": str(c), "TtlTradgVol": str(v)}


class CorporateActionTests(unittest.TestCase):
    def test_clean_bonus_back_adjusts_prices_and_volume(self):
        rows = [bar(200, 202, 198, 200, 1000), bar(200, 204, 199, 202, 1000), bar(101, 103, 100, 102, 2000)]
        out, events = adjust_corporate_actions(rows)
        self.assertEqual(events[0]["action"], "BACK-ADJUSTED")
        self.assertAlmostEqual(events[0]["applied_ratio"], 0.5)
        self.assertAlmostEqual(float(out[1]["ClsPric"]), 101.0)
        self.assertAlmostEqual(float(out[0]["TtlTradgVol"]), 2000.0)
        self.assertEqual(rows[1]["ClsPric"], "202")  # input never mutated

    def test_unclean_ratio_truncates_instead_of_guessing(self):
        rows = [bar(200, 202, 198, 200), bar(200, 204, 199, 202), bar(91, 93, 90, 92)]
        out, events = adjust_corporate_actions(rows)
        self.assertEqual(events[0]["action"], "HISTORY TRUNCATED")
        self.assertEqual(len(out), 1)

    def test_normal_moves_untouched(self):
        rows = [bar(100, 101, 99, 100), bar(108, 111, 107, 110)]
        out, events = adjust_corporate_actions(rows)
        self.assertEqual(events, [])
        self.assertEqual(out, rows)

    def test_split_no_longer_corrupts_ema(self):
        rows = []
        price = 1000.0
        for i in range(80):
            if i == 60:
                price /= 5  # 1:5 split
            rows.append(bar(price, price * 1.01, price * .99, price, 1000 if i < 60 else 5000))
        raw = compute_technicals(rows)
        fixed = compute_technicals(adjust_corporate_actions(rows)[0])
        self.assertGreater(raw["ema50"], 2 * raw["close"])
        self.assertAlmostEqual(fixed["ema50"], fixed["close"], delta=1)
        self.assertAlmostEqual(fixed["rvol20"], 1.0, delta=.01)


class SpecialSessionTests(unittest.TestCase):
    def test_special_sessions_in_history_but_not_scheduled_scan(self):
        for day in NSE_SPECIAL_SESSIONS_2026:
            self.assertTrue(history_session(day))
            self.assertIsNotNone(market_closure(day))
        self.assertFalse(history_session(date(2026, 11, 7)))   # ordinary Saturday
        self.assertFalse(history_session(date(2026, 11, 24)))  # listed holiday
        self.assertTrue(history_session(date(2026, 11, 23)))


class QualityGateTests(unittest.TestCase):
    tech = {"ema20": 102, "ema50": 100, "atr14": 2, "rvol20": 2.4, "close": 105}

    def plan(self, **kw):
        base = {"signal_id": "20261111-X-LONG-B-EXPERTPLAN", "symbol": "X", "direction": "LONG",
                "tier": "B — CONDITIONAL EXPERT TRADE PLAN", "entry_pattern": "breakout/breakdown",
                "cash_rvol20": 2.4, "cash_close": 105, "entry_trigger": 106, "stop_loss": 103,
                "pattern": "p", "futures_regime": "LONG BUILDUP", "unresolved_evidence": ["x"]}
        base.update(kw)
        return base

    def test_passing_b_plan(self):
        self.assertEqual(quality_gate(self.plan(), self.tech), (True, []))

    def test_low_rvol_demoted(self):
        ok, reasons = quality_gate(self.plan(cash_rvol20=MIN_RVOL - .01), self.tech)
        self.assertFalse(ok)
        self.assertIn("RVOL", reasons[0])

    def test_mature_trend_demoted(self):
        ok, reasons = quality_gate(self.plan(), {**self.tech, "ema20": 103})
        self.assertFalse(ok)
        self.assertIn("Mature trend", reasons[0])

    def test_roll_window_plans_are_watch_only(self):
        ok, reasons = quality_gate(self.plan(), self.tech, roll_window=True)
        self.assertFalse(ok)
        self.assertIn("roll window", reasons[0].lower())

    def test_short_trend_maturity_is_signed(self):
        self.assertAlmostEqual(trend_maturity_atr(self.tech, "LONG"), 1.0)
        self.assertAlmostEqual(trend_maturity_atr(self.tech, "SHORT"), -1.0)

    def test_c_breakout_demoted_but_c_pullback_allowed(self):
        c_break = self.plan(tier="C — CONDITIONAL EXPERT TRADE PLAN")
        c_pull = self.plan(tier="C — CONDITIONAL EXPERT TRADE PLAN",
                           entry_pattern="pullback to prior 20-session high, then bullish 5-minute reclaim")
        self.assertFalse(quality_gate(c_break, self.tech)[0])
        self.assertTrue(quality_gate(c_pull, self.tech)[0])

    def test_demoted_plan_renders_as_watch_without_levels_being_a_call(self):
        watch = demote_to_watch(self.plan(cash_rvol20=1.4), ["RVOL below"])
        self.assertTrue(watch["not_a_call"])
        self.assertIsNone(watch["recommendation"])
        report = render({"market_date": "2026-11-11", "requested_date": "2026-11-11",
                         "status": "VERIFIED EOD RESEARCH", "generated_ist": "x",
                         "errors": [], "candidates": [], "expert_trade_plans": [],
                         "expert_c_trade_plans": [], "expert_opportunities": [watch],
                         "coverage": {"quality_gate_demoted_to_watch": 1, "fno_breadth_above_ema20": .5}})
        self.assertIn("WATCH ONLY", report)
        self.assertIn("quality gate", report.lower())

    def test_market_chase_caution_is_directional(self):
        self.assertIsNotNone(market_context("LONG", .8)["market_chase_caution"])
        self.assertIsNone(market_context("SHORT", .8)["market_chase_caution"])
        self.assertIsNotNone(market_context("SHORT", .2)["market_chase_caution"])
        self.assertIsNone(market_context("LONG", None)["market_chase_caution"])

    def test_breadth_needs_enough_names(self):
        snaps = {str(i): {"tech": {"close": 10, "ema20": 9 if i < 15 else 11}} for i in range(30)}
        self.assertAlmostEqual(market_breadth(snaps), .5)
        self.assertIsNone(market_breadth({"A": {"tech": {"close": 1, "ema20": 1}}}))


class RollWindowTests(unittest.TestCase):
    def rows(self):
        return [{"XpryDt": "2026-11-24", "OpnIntrst": "1000", "ChngInOpnIntrst": "-400", "SttlmPric": "100"},
                {"XpryDt": "2026-12-29", "OpnIntrst": "900", "ChngInOpnIntrst": "450", "SttlmPric": "101"}]

    def test_outside_roll_window_uses_front_contract_unchanged(self):
        row, rolled = analysis_contract(self.rows(), date(2026, 11, 16))
        self.assertFalse(rolled)
        self.assertEqual(row["XpryDt"], "2026-11-24")
        self.assertEqual(row["OpnIntrst"], "1000")

    def test_roll_window_uses_next_contract_with_same_day_all_expiry_oi(self):
        rows = self.rows()
        row, rolled = analysis_contract(rows, date(2026, 11, 23))
        self.assertTrue(rolled)
        self.assertEqual(row["XpryDt"], "2026-12-29")
        self.assertEqual(float(row["OpnIntrst"]), 1900)
        self.assertEqual(float(row["ChngInOpnIntrst"]), 50)
        self.assertEqual(rows[1]["OpnIntrst"], "900")  # source rows untouched


class T1CapTests(unittest.TestCase):
    def setUp(self):
        self.tech = {"close": 105.5, "high": 106, "low": 104, "atr14": 2, "ema20": 102, "ema50": 100,
                     "rsi14": 62, "macd_hist": .4, "prev5_high": 104, "prev20_high": 104,
                     "prev5_low": 100, "prev20_low": 95, "fib_swing_high60": 115, "fib_swing_low60": 88,
                     "fib_levels60": {"0.786": 112}}
        self.idea = {"id": "20261111-S-LONG-EXPERT", "symbol": "S", "directional_bias": "LONG",
                     "pattern": "20-session cash breakout with participation", "pattern_priority": 4,
                     "market_date": "2026-11-11", "cash_close": 105.5, "relative_volume": 2.2,
                     "futures_regime": "LONG BUILDUP", "futures_change_pct": 1.5, "futures_oi_change_pct": 4.4,
                     "ema20": 102, "ema50": 100, "rsi14": 62, "macd_hist": .4,
                     "price_decision_level": 106.1, "indicative_invalidation": 103.8,
                     "caveats": [], "data_quality": "verified"}

    def test_far_structural_t1_is_capped_and_kept_as_t2(self):
        p = expert_trade_plan(self.idea, self.tech, {"near_call_wall": 113, "near_put_wall": 100})
        risk = 106.1 - 103.8
        self.assertTrue(p["t1_capped"])
        self.assertAlmostEqual(p["target_1"], round(106.1 + T1_CAP_R * risk, 2), places=2)
        self.assertIn("cap", p["target_sources"][0])
        self.assertGreater(p["structural_net_rr"], p["modelled_net_rr_t1"])
        self.assertLess(p["target_1"], p["target_2"])
        self.assertIn("level-based", p["target_sources"][1])

    def test_near_structural_t1_not_capped(self):
        p = expert_trade_plan(self.idea, self.tech, {"near_call_wall": 108.6, "near_put_wall": 100})
        self.assertFalse(p["t1_capped"])
        self.assertLessEqual(p["modelled_net_rr_t1"], T1_CAP_R)


if __name__ == "__main__":
    unittest.main()
