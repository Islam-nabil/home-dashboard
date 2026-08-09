import unittest
from engines import alerts


class TestAlerts(unittest.TestCase):
    def test_below_target_and_drop_10pct_and_new_low_all_fire_together(self):
        product = {"full_name": "LG Refrigerator GN-H722HLHL", "target_buy_price_egp": 27000}
        category = {"priority_level": 1}
        pricing = {"current_price": 25900, "previous_price": 29600, "historical_low": 29600, "availability": "in_stock"}
        triggered = alerts.evaluate_conditions(product, category, pricing, {"score": 94})
        types = {t["alert_type"] for t in triggered}
        self.assertIn("below_target", types)
        self.assertIn("drop_10pct", types)
        self.assertIn("new_low", types)
        self.assertIn("exceptional_deal", types)
        self.assertIn("high_priority_sale", types)

    def test_back_in_stock_only_on_transition(self):
        product = {"full_name": "X"}
        category = {"priority_level": 2}
        pricing = {"current_price": 1000, "previous_price": 1000, "historical_low": None, "availability": "in_stock"}
        triggered = alerts.evaluate_conditions(product, category, pricing, {"score": 50}, previous_availability="out_of_stock")
        types = {t["alert_type"] for t in triggered}
        self.assertIn("back_in_stock", types)

        triggered2 = alerts.evaluate_conditions(product, category, pricing, {"score": 50}, previous_availability="in_stock")
        types2 = {t["alert_type"] for t in triggered2}
        self.assertNotIn("back_in_stock", types2)

    def test_should_alert_prevents_spam_on_unchanged_price(self):
        last_alert = {"price_at_alert": 25000}
        self.assertFalse(alerts.should_alert("below_target", 25000, last_alert))
        self.assertFalse(alerts.should_alert("below_target", 25100, last_alert))  # <2% change
        self.assertTrue(alerts.should_alert("below_target", 24000, last_alert))   # >2% change

    def test_should_alert_new_low_requires_strictly_lower(self):
        last_alert = {"price_at_alert": 25000}
        self.assertFalse(alerts.should_alert("new_low", 25000, last_alert))
        self.assertFalse(alerts.should_alert("new_low", 25500, last_alert))
        self.assertTrue(alerts.should_alert("new_low", 24500, last_alert))

    def test_dedup_key_stable_for_identical_rerun(self):
        k1 = alerts.make_dedup_key(5, "below_target", 25900.4)
        k2 = alerts.make_dedup_key(5, "below_target", 25900.2)
        self.assertEqual(k1, k2)  # rounds to same bucket -> idempotent


if __name__ == "__main__":
    unittest.main()
