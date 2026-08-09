import unittest
from engines import budget


def make_categories():
    return [
        {"id": 1, "name": "Refrigerator", "priority_level": 1, "target_budget_egp": 35000},
        {"id": 2, "name": "Air Conditioner", "priority_level": 1, "target_budget_egp": 30000},
        {"id": 3, "name": "Microwave", "priority_level": 3, "target_budget_egp": 8000},
    ]


class TestBudget(unittest.TestCase):
    def test_spent_and_remaining_basic(self):
        categories = make_categories()
        products = [
            {"id": 10, "category_id": 1, "purchase_status": "purchased", "target_buy_price_egp": 34000, "current_price": None},
            {"id": 20, "category_id": 2, "purchase_status": "shortlisted", "target_buy_price_egp": 28000, "current_price": 30000},
            {"id": 30, "category_id": 3, "purchase_status": "shortlisted", "target_buy_price_egp": 7000, "current_price": 7500},
        ]
        purchases = [{"product_id": 10, "purchase_price_egp": 33000}]
        result = budget.compute_budget(180000, categories, products, purchases)
        self.assertEqual(result["spent_egp"], 33000)
        self.assertEqual(result["remaining_egp"], 180000 - 33000)
        self.assertEqual(result["critical_purchased"], 1)
        self.assertEqual(result["critical_total"], 2)
        # Category 2 (AC, priority1, unpurchased) contributes its current price (30000) to essential estimate
        self.assertEqual(result["estimated_remaining_essential_egp"], 30000)

    def test_committed_counts_ready_to_buy_not_yet_purchased(self):
        categories = make_categories()
        products = [
            {"id": 20, "category_id": 2, "purchase_status": "ready_to_buy", "target_buy_price_egp": 28000, "current_price": 29500},
        ]
        purchases = []
        result = budget.compute_budget(180000, categories, products, purchases)
        self.assertEqual(result["committed_egp"], 29500)
        self.assertEqual(result["remaining_egp"], 180000 - 29500)

    def test_buffer_goes_negative_when_essentials_unaffordable(self):
        categories = [{"id": 1, "name": "Refrigerator", "priority_level": 1, "target_budget_egp": 35000}]
        products = [{"id": 10, "category_id": 1, "purchase_status": "shortlisted", "target_buy_price_egp": 35000, "current_price": 40000}]
        purchases = []
        result = budget.compute_budget(30000, categories, products, purchases)
        self.assertLess(result["buffer_egp"], 0)
        self.assertEqual(result["risk_level"], "over_budget")

    def test_simulate_purchases_updates_remaining_and_critical_gap(self):
        categories = make_categories()
        products = [
            {"id": 10, "category_id": 1, "purchase_status": "shortlisted", "target_buy_price_egp": 34000, "current_price": 33000},
            {"id": 20, "category_id": 2, "purchase_status": "shortlisted", "target_buy_price_egp": 28000, "current_price": 29000},
        ]
        purchases = []
        sim = budget.simulate_purchases(180000, categories, products, purchases,
                                         [{"product_id": 10, "price_egp": 33000}])
        self.assertEqual(sim["delta_remaining_egp"], -33000)
        remaining_critical = [c["category_id"] for c in sim["remaining_critical_categories"]]
        self.assertIn(2, remaining_critical)
        self.assertNotIn(1, remaining_critical)


if __name__ == "__main__":
    unittest.main()
