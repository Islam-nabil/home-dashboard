import unittest
from engines import scoring


class TestScoring(unittest.TestCase):
    def test_full_breakdown_weighted_average(self):
        breakdown = {
            "reliability": 90, "price_value": 80, "warranty_service": 70,
            "energy_efficiency": 60, "performance": 85, "features": 50,
            "user_preference": 100,
        }
        weights = {
            "reliability": 0.30, "price_value": 0.20, "warranty_service": 0.15,
            "energy_efficiency": 0.10, "performance": 0.15, "features": 0.05,
            "user_preference": 0.05,
        }
        score, detail = scoring.compute_product_score(breakdown, weights)
        expected = (90*.3 + 80*.2 + 70*.15 + 60*.1 + 85*.15 + 50*.05 + 100*.05)
        self.assertAlmostEqual(score, round(expected, 1), places=1)
        self.assertEqual(len(detail["dimensions"]), 7)

    def test_missing_dimensions_are_renormalized_not_zeroed(self):
        # Only reliability and price_value scored; score should reflect
        # ONLY those two dims re-weighted to sum to 1, not be dragged down
        # by treating the other 5 dims as zero.
        breakdown = {"reliability": 100, "price_value": 100}
        weights = {"reliability": 0.30, "price_value": 0.20}
        score, detail = scoring.compute_product_score(breakdown, weights)
        self.assertEqual(score, 100.0)
        self.assertEqual(len(detail["unscored_dimensions"]), 5)

    def test_empty_breakdown_returns_none(self):
        score, detail = scoring.compute_product_score({}, {})
        self.assertIsNone(score)

    def test_default_weights_used_when_category_has_none(self):
        breakdown = {"reliability": 80}
        score, _ = scoring.compute_product_score(breakdown, {})
        self.assertEqual(score, 80.0)

    def test_normalize_weights_sums_to_one(self):
        w = scoring.normalize_weights({"reliability": 3, "price_value": 1})
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
