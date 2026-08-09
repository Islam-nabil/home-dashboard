import unittest
from engines import recommendation, deal_score


class TestRecommendation(unittest.TestCase):
    def test_critical_scenario_microwave_good_discount_but_jeopardizes_priority1_is_not_buy(self):
        """The example from the spec's testing section: a low-priority
        microwave gets a good discount, but buying it would put the
        remaining Priority-1 budget at risk -> must NOT be BUY/URGENT_BUY."""
        product = {"target_buy_price_egp": 7000, "ai_research_score": 75}
        category = {"priority_level": 3, "id": 3, "name": "Microwave"}
        pricing = {
            "current_price": 6000, "historical_low": 6500, "historical_high": 8500,
            "historical_avg": 8000, "target_buy_price_egp": 7000, "num_observations": 10,
        }
        deal = deal_score.compute_deal_score(pricing, quality_score=75, retailer_credibility=80)
        self.assertGreaterEqual(deal["score"], 75)  # confirm it IS a good discount

        budget_summary = {
            "remaining_egp": 40000,
            # Other unfunded Priority-1 categories need 38000 -> buying this
            # 6000 microwave would leave only 34000, below that need.
            "other_priority1_gap_egp": 38000,
        }
        result = recommendation.recommend(product, category, deal, budget_summary, current_price=6000)
        self.assertNotIn(result["decision"], ("BUY", "URGENT_BUY"))
        self.assertIn("jeopardizes_priority1_budget", result["risk_flags"])

    def test_refrigerator_at_historical_low_with_budget_is_urgent_buy(self):
        product = {"target_buy_price_egp": 27000, "ai_research_score": 95}
        category = {"priority_level": 1, "id": 1, "name": "Refrigerator"}
        pricing = {
            "current_price": 25000, "historical_low": 29600, "historical_high": 32000,
            "historical_avg": 29800, "target_buy_price_egp": 27000, "num_observations": 12,
        }
        deal = deal_score.compute_deal_score(pricing, quality_score=95, retailer_credibility=95)
        self.assertGreaterEqual(deal["score"], 90)
        budget_summary = {"remaining_egp": 150000, "other_priority1_gap_egp": 60000}
        result = recommendation.recommend(product, category, deal, budget_summary, current_price=25000)
        self.assertEqual(result["decision"], "URGENT_BUY")

    def test_cannot_afford_is_ignore_regardless_of_deal_quality(self):
        product = {"target_buy_price_egp": 27000, "ai_research_score": 90}
        category = {"priority_level": 1, "id": 1, "name": "Refrigerator"}
        pricing = {
            "current_price": 25900, "historical_low": 29600, "historical_high": 32000,
            "historical_avg": 29800, "target_buy_price_egp": 27000, "num_observations": 12,
        }
        deal = deal_score.compute_deal_score(pricing, quality_score=90, retailer_credibility=85)
        budget_summary = {"remaining_egp": 10000, "other_priority1_gap_egp": 0}
        result = recommendation.recommend(product, category, deal, budget_summary, current_price=25900)
        self.assertEqual(result["decision"], "IGNORE")
        self.assertIn("exceeds_remaining_budget", result["risk_flags"])

    def test_poor_deal_is_ignored(self):
        product = {"target_buy_price_egp": 20000, "ai_research_score": 70}
        category = {"priority_level": 2, "id": 2, "name": "TV"}
        pricing = {
            "current_price": 30000, "historical_low": 22000, "historical_high": 24000,
            "historical_avg": 23000, "target_buy_price_egp": 20000, "num_observations": 10,
        }
        deal = deal_score.compute_deal_score(pricing, quality_score=70, retailer_credibility=80)
        budget_summary = {"remaining_egp": 150000, "other_priority1_gap_egp": 0}
        result = recommendation.recommend(product, category, deal, budget_summary, current_price=30000)
        self.assertEqual(result["decision"], "IGNORE")


if __name__ == "__main__":
    unittest.main()
