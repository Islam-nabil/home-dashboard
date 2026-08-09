import unittest
from engines import deal_score


class TestDealScore(unittest.TestCase):
    def test_no_price_data(self):
        result = deal_score.compute_deal_score({"current_price": None})
        self.assertIsNone(result["score"])
        self.assertEqual(result["confidence"], "none")

    def test_new_low_and_below_target_scores_high(self):
        pricing = {
            "current_price": 25900,
            "historical_low": 29600,
            "historical_high": 32000,
            "historical_avg": 29800,
            "target_buy_price_egp": 27000,
            "num_observations": 12,
        }
        result = deal_score.compute_deal_score(pricing, quality_score=88, retailer_credibility=85)
        self.assertGreaterEqual(result["score"], 85)
        self.assertIn(result["label"], ("Good Buy", "Exceptional Deal"))
        self.assertTrue(any("new historical low" in e.lower() for e in result["explanation"]))

    def test_price_above_average_and_target_scores_low(self):
        pricing = {
            "current_price": 35000,
            "historical_low": 28000,
            "historical_high": 32000,
            "historical_avg": 29000,
            "target_buy_price_egp": 27000,
            "num_observations": 10,
        }
        result = deal_score.compute_deal_score(pricing, quality_score=70, retailer_credibility=80)
        self.assertLess(result["score"], 40)

    def test_thin_data_caps_confidence_and_score(self):
        pricing = {
            "current_price": 10000,
            "historical_low": 20000,  # implausible single obs (this IS the only obs)
            "historical_high": 20000,
            "historical_avg": 20000,
            "target_buy_price_egp": 15000,
            "num_observations": 1,
        }
        result = deal_score.compute_deal_score(pricing, quality_score=90, retailer_credibility=90)
        self.assertEqual(result["confidence"], "low")
        self.assertLessEqual(result["score"], 78)
        self.assertLess(result["score"], 90)  # never "Exceptional" on a single observation

    def test_low_quality_product_drags_score_down_despite_discount(self):
        pricing = {
            "current_price": 8000,
            "historical_low": 8000,
            "historical_high": 12000,
            "historical_avg": 11000,
            "target_buy_price_egp": 9000,
            "num_observations": 8,
        }
        good_quality = deal_score.compute_deal_score(pricing, quality_score=95, retailer_credibility=90)
        poor_quality = deal_score.compute_deal_score(pricing, quality_score=20, retailer_credibility=90)
        self.assertGreater(good_quality["score"], poor_quality["score"])


if __name__ == "__main__":
    unittest.main()
