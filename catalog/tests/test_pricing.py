from decimal import Decimal

from django.test import SimpleTestCase

from catalog.pricing import compute_totals, line_amount, margin_rate, price_from_cost, round_up_to


class PricingTests(SimpleTestCase):
    def test_line_amount_rounds_half_up(self):
        self.assertEqual(line_amount(Decimal("1.5"), 333), 500)   # 499.5 → 500
        self.assertEqual(line_amount(Decimal("2.25"), 1000), 2250)
        self.assertEqual(line_amount("0.333", 1000), 333)

    def test_tax_is_computed_once_per_rate_and_truncated(self):
        # 明細ごとに計算すると 99.9→99 ×3 = 297 になるが、税率ごとに1回なら 2997×10% = 299
        totals = compute_totals([(999, 10), (999, 10), (999, 10)])
        self.assertEqual(totals.subtotal, 2997)
        self.assertEqual(totals.tax, 299)
        self.assertEqual(totals.total, 3296)

    def test_mixed_rates(self):
        totals = compute_totals([(10000, 10), (1080, 8), (500, 0)])
        self.assertEqual([(b.rate, b.base, b.tax) for b in totals.rows], [(10, 10000, 1000), (8, 1080, 86), (0, 500, 0)])
        self.assertEqual(totals.total, 11580 + 1086)

    def test_price_from_cost(self):
        self.assertEqual(price_from_cost(7000, 30, 1), 10000)
        self.assertEqual(price_from_cost(7001, 30, 100), 10100)  # 10001.4… → 100円単位で切り上げ
        self.assertEqual(round_up_to(12001, 1000), 13000)
        with self.assertRaises(ValueError):
            price_from_cost(100, 100)

    def test_margin_rate(self):
        self.assertEqual(margin_rate(10000, 7000), 30.0)
        self.assertIsNone(margin_rate(0, 100))
