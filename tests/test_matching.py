import unittest
from engines import matching


class TestMatching(unittest.TestCase):
    def test_exact_sku_match(self):
        candidate = {"sku": "abc-123", "brand": "LG", "model": "GN-H722HLHL"}
        existing = {"sku": "ABC123", "brand": "LG", "model": "different-string"}
        confidence, score, _ = matching.match_confidence(candidate, existing)
        self.assertEqual(confidence, "sku")
        self.assertEqual(score, 1.0)

    def test_exact_model_match_case_and_symbol_insensitive(self):
        candidate = {"model": "gn-h722hlhl"}
        existing = {"model": "GN H722HLHL"}
        confidence, score, _ = matching.match_confidence(candidate, existing)
        self.assertEqual(confidence, "exact_model")

    def test_capacity_only_is_low_confidence_spec_similarity(self):
        candidate = {"brand": "LG", "model": "", "capacity": "506L"}
        existing = {"brand": "LG", "model": "", "capacity": "506L"}
        confidence, score, _ = matching.match_confidence(candidate, existing)
        self.assertEqual(confidence, "spec_similarity")
        self.assertLess(score, 0.6)

    def test_unrelated_products_are_uncertain_never_silently_merged(self):
        candidate = {"brand": "LG", "model": "XYZ999", "capacity": "506L"}
        existing = {"brand": "Samsung", "model": "ABC111", "capacity": "400L"}
        confidence, score, _ = matching.match_confidence(candidate, existing)
        self.assertEqual(confidence, "uncertain")
        self.assertEqual(score, 0.0)

    def test_find_best_match_picks_highest_score(self):
        candidate = {"sku": "", "brand": "LG", "model": "GN-H722HLHL", "capacity": "506L"}
        existing_products = [
            {"id": 1, "brand": "Samsung", "model": "RT-something", "capacity": "400L"},
            {"id": 2, "brand": "LG", "model": "GN-H722HLHL", "capacity": "506L"},
        ]
        best = matching.find_best_match(candidate, existing_products)
        self.assertIsNotNone(best)
        self.assertEqual(best["product"]["id"], 2)
        self.assertEqual(best["confidence"], "exact_model")


if __name__ == "__main__":
    unittest.main()
