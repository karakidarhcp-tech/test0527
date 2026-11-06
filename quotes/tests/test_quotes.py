from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import CompanySettings, Item
from deals.models import Customer, Deal
from documents.models import IssuedDocument
from quotes.models import LineMaterial, Quote, QuoteLine

User = get_user_model()


def line_post(rows, prefix="lines", existing=0):
    data = {f"{prefix}-TOTAL_FORMS": len(rows), f"{prefix}-INITIAL_FORMS": existing,
            f"{prefix}-MIN_NUM_FORMS": 0, f"{prefix}-MAX_NUM_FORMS": 1000}
    for i, row in enumerate(rows):
        for k, v in row.items():
            data[f"{prefix}-{i}-{k}"] = v
    return data


class QuoteFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="pw-123456!")
        self.client.force_login(self.user)
        s = CompanySettings.load()
        s.labor_rate, s.target_margin, s.price_rounding = 4000, Decimal("30"), 100
        s.save()
        self.deal = Deal.objects.create(title="造作家具", customer=Customer.objects.create(name="杢工房"),
                                        site_address="東京都港区")

    def create_quote(self):
        self.client.post(reverse("quote_create", args=[self.deal.pk]))
        return Quote.objects.latest("id")

    def header(self, q, **kw):
        d = {"title": q.title, "issue_date": "2026-11-06", "valid_until": "2026-12-06", "delivery_terms": "",
             "delivery_place": "", "notes": "", "internal_memo": ""}
        d.update(kw)
        return d

    def test_create_uses_number_and_snapshots_settings(self):
        q = self.create_quote()
        self.assertEqual(q.number, f"{self.deal.number}-Q1")
        self.assertEqual((q.labor_rate, q.target_margin, q.delivery_place), (4000, Decimal("30.0"), "東京都港区"))
        s = CompanySettings.load()
        s.labor_rate = 9999
        s.save()
        q.refresh_from_db()
        self.assertEqual(q.labor_rate, 4000)  # 設定を変えても過去の見積は変わらない

    def test_edit_lines_and_totals(self):
        q = self.create_quote()
        data = self.header(q)
        data.update(line_post([
            {"name": "壁面収納", "spec": "W1800", "quantity": "2", "unit": "台", "unit_price": "150000", "tax_rate": "10", "direct_cost": "0"},
            {"name": "", "spec": "", "quantity": "1", "unit": "式", "unit_price": "5000", "tax_rate": "10", "direct_cost": "0"},
            {"name": "運搬設置費", "quantity": "1", "unit": "式", "unit_price": "33333", "tax_rate": "10", "direct_cost": "20000"},
        ]))
        resp = self.client.post(reverse("quote_edit", args=[q.pk]), data)
        self.assertEqual(resp.status_code, 200)  # 2 行目: 金額があるのに品名が空 → エラー
        self.assertFalse(q.lines.exists())
        data.update(line_post([
            {"name": "壁面収納", "spec": "W1800", "quantity": "2", "unit": "台", "unit_price": "150000", "tax_rate": "10", "direct_cost": "0"},
            {"name": "", "spec": "", "quantity": "1", "unit": "式", "unit_price": "0", "tax_rate": "10", "direct_cost": "0"},
            {"name": "運搬設置費", "quantity": "1", "unit": "式", "unit_price": "33333", "tax_rate": "10", "direct_cost": "20000"},
        ]))
        # 何も入力していない空行は無視して保存できる
        self.assertRedirects(self.client.post(reverse("quote_edit", args=[q.pk]), data), q.get_absolute_url())
        self.assertEqual([ln.position for ln in q.lines.all()], [1, 2])
        t = q.totals
        self.assertEqual((t.subtotal, t.tax, t.total), (333333, 33333, 366666))

    def test_line_cost_materials_labor_and_apply_price(self):
        q = self.create_quote()
        line = QuoteLine.objects.create(quote=q, name="キャビネット", quantity=Decimal("3"), unit="台", unit_price=0)
        board = Item.objects.create(name="シナランバー", unit="枚", cost=Decimal("9800"))
        data = {"production_hours": "6", "direct_cost": "2000"}
        data.update(line_post([
            {"item": board.pk, "name": board.name, "spec": "", "unit": "枚", "quantity": "1.5", "unit_cost": "9800"},
            {"item": "", "name": "スライド蝶番", "spec": "", "unit": "個", "quantity": "4", "unit_cost": "480.5"},
        ], prefix="mat"))
        data["apply_price"] = "1"
        resp = self.client.post(reverse("quote_line_cost", args=[q.pk, line.pk]), data)
        self.assertEqual(resp.status_code, 302)
        line.refresh_from_db()
        # 材料 14700 + 1922 = 16622、労務 6h×4000 = 24000、その他 2000 → 原価 42622/台
        self.assertEqual(line.unit_cost, Decimal("42622.000"))
        # 42622 ÷ 0.7 = 60888.57 → 100円単位で切り上げ 60900
        self.assertEqual(line.unit_price, 60900)
        cost = q.cost_summary
        self.assertEqual((cost["material"], cost["labor"], cost["direct"]), (49866, 72000, 6000))
        self.assertEqual(cost["hours"], Decimal("18"))
        self.assertEqual(cost["profit"], 182700 - 127866)

    def test_copy_creates_next_version_with_independent_lines(self):
        q = self.create_quote()
        line = QuoteLine.objects.create(quote=q, name="棚", unit_price=1000)
        LineMaterial.objects.create(line=line, name="板", quantity=2, unit_cost=100)
        self.client.post(reverse("quote_copy", args=[q.pk]))
        q2 = Quote.objects.latest("id")
        self.assertEqual((q2.number, q2.version, q2.copied_from), (f"{self.deal.number}-Q2", 2, q))
        l2 = q2.lines.get()
        self.assertEqual(l2.materials.get().quantity, 2)
        l2.name = "変更"
        l2.save()
        self.assertEqual(QuoteLine.objects.get(pk=line.pk).name, "棚")

    def test_issue_archives_pdf_and_locks(self):
        q = self.create_quote()
        QuoteLine.objects.create(quote=q, name="棚", unit_price=100000)
        self.client.post(reverse("quote_issue", args=[q.pk]))
        q.refresh_from_db()
        self.assertEqual(q.status, Quote.Status.SUBMITTED)
        doc = IssuedDocument.objects.get(number=q.number)
        self.assertTrue(bytes(doc.pdf).startswith(b"%PDF"))
        self.assertEqual((doc.total, doc.customer_name, doc.deal_number), (110000, "杢工房", self.deal.number))
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.phase, Deal.Phase.ESTIMATE)
        # 発行済みは編集不可・削除不可、PDF は保存した原本を返す
        self.assertRedirects(self.client.get(reverse("quote_edit", args=[q.pk])), q.get_absolute_url())
        self.client.post(reverse("quote_delete", args=[q.pk]))
        self.assertTrue(Quote.objects.filter(pk=q.pk).exists())
        resp = self.client.get(reverse("quote_pdf", args=[q.pk]))
        self.assertEqual(b"".join(resp), bytes(doc.pdf))

    def test_issue_requires_lines(self):
        q = self.create_quote()
        self.client.post(reverse("quote_issue", args=[q.pk]))
        q.refresh_from_db()
        self.assertEqual(q.status, Quote.Status.DRAFT)

    def test_pages_render(self):
        q = self.create_quote()
        line = QuoteLine.objects.create(quote=q, name="棚", unit_price=1000)
        for url in [reverse("quote_list"), reverse("quote_edit", args=[q.pk]), q.get_absolute_url(),
                    reverse("quote_line_cost", args=[q.pk, line.pk]), self.deal.get_absolute_url()]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        resp = self.client.get(reverse("quote_pdf", args=[q.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
