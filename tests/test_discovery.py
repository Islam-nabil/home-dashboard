"""
End-to-end tests for the "New Finds" review-queue lifecycle: a scan result
becomes a product_candidates row, which a human then approves (-> a real
product/listing/price observation, same shape as a wishlist confirm) or
dismisses (-> stays out of the catalog). Runs against a real temp SQLite
DB (no mocking) since this is genuinely new schema + repository code that
hasn't been exercised anywhere else.
"""
import os
import tempfile
import unittest


class TestDiscoveryLifecycle(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmp_dir, "test.db")

        import config
        config.DATABASE_PATH = self._db_path

        import db
        # Each test gets a fresh thread-local connection bound to the temp DB.
        db._local.conn = None
        self.db = db
        db.init_db()

        import repository as repo
        self.repo = repo

        self.category_id = repo.create_category({
            "key": "refrigerator", "name": "Refrigerator", "icon": "🧊",
            "priority_level": 1, "target_budget_egp": 35000,
        })
        self.retailer = repo.get_or_create_retailer(
            "btech", name="B.TECH", provider_key="btech", render_mode="js", allow_category_scan=True,
        )

    def tearDown(self):
        import db
        if getattr(db._local, "conn", None) is not None:
            db._local.conn.close()
            db._local.conn = None

    def test_create_candidate_then_list_pending(self):
        self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Sharp Freestanding Refrigerator 18ft", url="https://btech.com/en/p/sharp-fridge-18ft",
            brand_guess="Sharp", model_guess="SJ-GV58A", price_egp=42634,
        )
        pending = self.repo.list_candidates(status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["full_name"], "Sharp Freestanding Refrigerator 18ft")
        self.assertEqual(self.repo.count_pending_candidates(), 1)

    def test_duplicate_url_is_silently_ignored_not_a_second_candidate(self):
        url = "https://btech.com/en/p/sharp-fridge-18ft"
        first = self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Sharp Freestanding Refrigerator 18ft", url=url, price_egp=42634,
        )
        second = self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Sharp Freestanding Refrigerator 18ft", url=url, price_egp=42634,
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)  # UNIQUE(url) violation -> None, not a crash
        self.assertEqual(len(self.repo.list_candidates(status="pending")), 1)

    def test_approve_candidate_creates_real_product_and_listing(self):
        candidate_id = self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Sharp Freestanding Refrigerator 18ft", url="https://btech.com/en/p/sharp-fridge-18ft",
            brand_guess="Sharp", model_guess="SJ-GV58A", price_egp=42634,
            image_url="https://media.btech.com/catalogs/sharp.jpg",
        )
        product_id = self.repo.approve_candidate(candidate_id, actor="Islam")
        self.assertIsNotNone(product_id)

        product = self.repo.get_product(product_id)
        self.assertEqual(product["full_name"], "Sharp Freestanding Refrigerator 18ft")
        self.assertEqual(product["brand"], "Sharp")
        self.assertEqual(len(product["listings"]), 1)
        self.assertEqual(product["pricing"]["current_price"], 42634)

        # The candidate itself is marked reviewed, not left pending forever.
        self.assertEqual(self.repo.count_pending_candidates(), 0)
        reviewed = self.repo.get_candidate(candidate_id)
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["reviewed_by"], "Islam")

    def test_dismiss_candidate_never_creates_a_product(self):
        candidate_id = self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Random unrelated listing", url="https://btech.com/en/p/random",
        )
        ok = self.repo.dismiss_candidate(candidate_id, actor="Salma")
        self.assertTrue(ok)
        self.assertEqual(self.repo.count_pending_candidates(), 0)
        self.assertEqual(len(self.repo.list_products(with_pricing=False)), 0)

    def test_cannot_review_the_same_candidate_twice(self):
        candidate_id = self.repo.create_candidate(
            category_id=self.category_id, retailer_id=self.retailer["id"],
            full_name="Sharp Freestanding Refrigerator 18ft", url="https://btech.com/en/p/sharp-fridge-18ft",
        )
        self.repo.dismiss_candidate(candidate_id, actor="Islam")
        # Second dismiss/approve on an already-reviewed candidate is a no-op, not a crash.
        self.assertFalse(self.repo.dismiss_candidate(candidate_id, actor="Salma"))
        self.assertIsNone(self.repo.approve_candidate(candidate_id, actor="Salma"))

    def test_list_scan_price_targets_only_returns_js_render_mode_listings(self):
        static_retailer = self.repo.get_or_create_retailer("twob", name="2B Egypt", render_mode="static")
        product_id = self.repo.create_product({
            "category_id": self.category_id, "brand": "Fresh", "model": "FNT-BR470KT",
            "full_name": "Fresh Fridge",
        })
        js_listing = self.repo.add_listing(product_id, self.retailer["id"], url="https://btech.com/en/p/fresh")
        self.repo.add_listing(product_id, static_retailer["id"], url="https://2b.com.eg/en/fresh.html")

        targets = self.repo.list_scan_price_targets()
        listing_ids = {t["listing_id"] for t in targets}
        self.assertIn(js_listing, listing_ids)
        self.assertEqual(len(targets), 1)  # the static (2B) listing must NOT show up here

    def test_discovery_sources_excludes_retailers_without_allow_category_scan(self):
        twob = self.repo.get_or_create_retailer("twob", name="2B Egypt", render_mode="static", allow_category_scan=False)
        self.db.insert("discovery_sources", {
            "category_id": self.category_id, "retailer_id": twob["id"],
            "listing_url": "https://2b.com.eg/en/refrigerators.html", "is_active": 1,
            "last_scanned_at": "", "created_at": self.db.now_iso(),
        })
        self.db.insert("discovery_sources", {
            "category_id": self.category_id, "retailer_id": self.retailer["id"],
            "listing_url": "https://btech.com/en/c/large-home-appliances/refrigerators", "is_active": 1,
            "last_scanned_at": "", "created_at": self.db.now_iso(),
        })
        sources = self.repo.list_discovery_sources()
        retailer_keys = {s["retailer_key"] for s in sources}
        self.assertEqual(retailer_keys, {"btech"})  # 2B never appears, even though a row exists for it


if __name__ == "__main__":
    unittest.main()
