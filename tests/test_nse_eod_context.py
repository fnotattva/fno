"""Positioning context: futures premium caution, delivery %, OI-as-context wording."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"/"nse_eod"))
import data
from quality import futures_premium_ranks, premium_context, delivery_context
from management import review_research_plans


def snaps(premiums):
    return {s: {"future": {"SttlmPric": str(100 * (1 + p)), "UndrlygPric": "100"}} for s, p in premiums.items()}


class PremiumTests(unittest.TestCase):
    def setUp(self):
        prem = {f"S{i}": (i - 15) / 10000 for i in range(30)}   # -0.15% .. +0.14%
        prem["DIV"] = -0.06                                         # corporate-event distortion
        self.ranks = futures_premium_ranks(snaps(prem))

    def test_rank_order_and_distortion(self):
        self.assertAlmostEqual(self.ranks["S0"][1], 0.0)
        self.assertAlmostEqual(self.ranks["S29"][1], 1.0)
        self.assertIsNone(self.ranks["DIV"][1])

    def test_caution_is_directional(self):
        low, high = self.ranks["S2"], self.ranks["S27"]
        self.assertIsNotNone(premium_context("LONG", *low)["futures_premium_caution"])
        self.assertIsNone(premium_context("SHORT", *low)["futures_premium_caution"])
        self.assertIsNotNone(premium_context("SHORT", *high)["futures_premium_caution"])
        self.assertIsNone(premium_context("LONG", *high)["futures_premium_caution"])
        self.assertIn("corporate", premium_context("LONG", *self.ranks["DIV"])["futures_premium_caution"])

    def test_missing_premium(self):
        self.assertIsNone(premium_context("LONG", None, None)["futures_premium_pct"])


class DeliveryTests(unittest.TestCase):
    CSV = ("SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, "
           "AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
           "ABC, EQ, 20-Nov-2026, 1,1,1,1,1,1,1,100,1,1,60,60.00\n"
           "ABC, BE, 20-Nov-2026, 1,1,1,1,1,1,1,100,1,1,-,-\n"
           "XYZ, EQ, 20-Nov-2026, 1,1,1,1,1,1,1,100,1,1,30,30.50\n")

    def test_parse_eq_only(self):
        with mock.patch.object(data, "_download", return_value=self.CSV.encode()):
            out = data.load_delivery(date(2026, 11, 20))
        self.assertEqual(out, {"ABC": 60.0, "XYZ": 30.5})

    def test_date_mismatch_rejected(self):
        with mock.patch.object(data, "_download", return_value=self.CSV.encode()):
            with self.assertRaises(data.Unavailable):
                data.load_delivery(date(2026, 11, 19))

    def test_relative_needs_history(self):
        hist = [{"ABC": 40.0}] * 20
        self.assertEqual(delivery_context("ABC", {"ABC": 60.0}, hist), {"delivery_pct": 60.0, "delivery_rel20": 1.5})
        self.assertIsNone(delivery_context("ABC", {"ABC": 60.0}, hist[:5])["delivery_rel20"])
        self.assertIsNone(delivery_context("NONE", {"ABC": 60.0}, hist)["delivery_pct"])


class OIContextWordingTests(unittest.TestCase):
    def test_opposing_oi_alone_is_not_an_exit(self):
        sig = {"signal_id": "20261111-DEMO-LONG-B-EXPERTPLAN", "symbol": "DEMO", "direction": "LONG",
               "market_date": "2026-11-11", "entry_trigger": 106.0, "stop_loss": 102.0,
               "target_1": 110.0, "target_2": 112.0, "target_3": 114.0, "valid_for_next_sessions": 2}
        item = {"asof_date": "2026-11-11", "last_checked": "2026-11-11", "observed_sessions": 0, "signal": sig}
        snap = {"future": {"SttlmPric": "99", "PrvsClsgPric": "100", "OpnIntrst": "11000", "ChngInOpnIntrst": "1000"},
                "chain": {"near_put_wall": 95, "near_call_wall": 115},
                "tech": {"atr14": 2, "ema20": 103, "prev5_low": 100, "prev5_high": 108, "rsi14": 60, "macd_hist": .4}}
        candle = {"DEMO": {"HghPric": "107", "LwPric": "105", "ClsPric": "106.5"}}
        u, k = review_research_plans([item], date(2026, 11, 12), candle, {"DEMO": snap})
        self.assertEqual(u[0]["futures_regime_today"], "SHORT BUILDUP")
        self.assertIn("OI CONTEXT ONLY", u[0]["action_if_filled"])
        self.assertNotIn("EXIT IF FILLED", u[0]["action_if_filled"])
        self.assertFalse(u[0]["terminal_for_scenario"])
        self.assertEqual(len(k), 1)


if __name__ == "__main__":
    unittest.main()
