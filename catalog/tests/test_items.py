import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from catalog.importer import import_items
from catalog.models import CompanySettings, Item

User = get_user_model()


def xlsx(rows):
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("原価表.xlsx", buf.getvalue())


class ImporterTests(TestCase):
    def test_import_with_title_rows_and_alias_headers(self):
        f = xlsx([
            ["2026年度 原価表"], [],
            ["コード", "区分", "名称", "サイズ", "単位", "仕入単価", "備考"],
            ["W-001", "板材・合板", "シナランバー", "21mm", "枚", "¥9,800", ""],
            [None, "金物", "スライド蝶番　全かぶせ", None, "個", 480.5, "メモ"],
            [], [None, None, None, None, None, None, None],
        ])
        r = import_items(f)
        self.assertEqual(r.errors, [])
        self.assertEqual((r.created, r.updated), (2, 0))
        w = Item.objects.get(code="W-001")
        self.assertEqual((w.category, w.cost, w.unit), ("board", Decimal("9800.00"), "枚"))
        h = Item.objects.get(name="スライド蝶番 全かぶせ")
        self.assertEqual((h.category, h.cost, h.notes), ("hardware", Decimal("480.50"), "メモ"))

    def test_reimport_updates_by_code_or_name_spec(self):
        import_items(xlsx([["品番", "品名", "規格", "原価"], ["A1", "板", "", 100], ["", "ビス", "M4", 5]]))
        r = import_items(xlsx([["品番", "品名", "規格", "原価"], ["A1", "板（改）", "", 120], ["", "ビス", "M4", 6]]))
        self.assertEqual((r.created, r.updated), (0, 2))
        self.assertEqual(Item.objects.get(code="A1").name, "板（改）")
        self.assertEqual(Item.objects.get(name="ビス").cost, Decimal("6.00"))

    def test_any_error_imports_nothing(self):
        r = import_items(xlsx([["品名", "原価"], ["板", 100], ["釘", "abc"], ["", 50], ["ネジ", -1]]))
        self.assertEqual(Item.objects.count(), 0)
        self.assertEqual([row for row, _ in r.errors], [3, 4, 5])

    def test_missing_columns(self):
        self.assertIn("見出し行", import_items(xlsx([["a", "b"], [1, 2]])).errors[0][1])
        self.assertIn("原価", import_items(xlsx([["品名", "単位"], ["板", "枚"]])).errors[0][1])

    def test_shift_jis_csv(self):
        data = "品名,単位,原価\n天板,枚,12000\n".encode("cp932")
        r = import_items(SimpleUploadedFile("cost.csv", data))
        self.assertEqual(r.created, 1)
        self.assertEqual(Item.objects.get().name, "天板")

    def test_unsupported_file(self):
        r = import_items(SimpleUploadedFile("old.xls", b"\xd0\xcf"))
        self.assertIn(".xlsx", r.errors[0][1])


class ItemViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="pw-123456!")
        self.staff = User.objects.create_user("s", password="pw-123456!", is_staff=True)
        self.client.force_login(self.user)

    def test_pages(self):
        Item.objects.create(name="板", cost=Decimal("700"))
        for name in ["item_list", "item_create", "item_import"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        # 売価未設定 → 参考売価 700/(1-0.3)=1000
        self.assertContains(self.client.get(reverse("item_list")), "¥1,000")

    def test_template_download_roundtrip(self):
        resp = self.client.get(reverse("item_template"))
        self.assertEqual(resp.status_code, 200)
        f = SimpleUploadedFile("t.xlsx", resp.content)
        self.assertEqual(import_items(f).created, 3)
        load_workbook(io.BytesIO(resp.content))  # 壊れていないこと

    def test_import_view(self):
        resp = self.client.post(reverse("item_import"), {"file": xlsx([["品名", "原価"], ["板", 100]])})
        self.assertRedirects(resp, reverse("item_list"))
        resp = self.client.post(reverse("item_import"), {"file": xlsx([["品名", "原価"], ["板", "x"]])})
        self.assertContains(resp, "2行目")

    def test_search_json(self):
        Item.objects.create(name="シナ合板", code="S1", cost=1)
        Item.objects.create(name="停止品", cost=1, is_active=False)
        data = self.client.get(reverse("item_search_json"), {"q": "シナ"}).json()
        self.assertEqual([i["label"] for i in data["items"]], ["[S1] シナ合板"])

    def test_settings_staff_only(self):
        self.assertEqual(self.client.get(reverse("company_settings")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("company_settings")).status_code, 200)
        resp = self.client.post(reverse("company_settings"), {
            "company_name": "杢匠", "registration_number": "T123", "quote_valid_days": 30, "labor_rate": 4000,
            "target_margin": "30", "price_rounding": 100, "deposit_percent": 50, "interim_percent": 0})
        self.assertContains(resp, "T + 13桁")
        resp = self.client.post(reverse("company_settings"), {
            "company_name": "杢匠", "registration_number": "T1234567890123", "quote_valid_days": 30,
            "labor_rate": 4000, "target_margin": "30", "price_rounding": 100, "deposit_percent": 60,
            "interim_percent": 50})
        self.assertContains(resp, "100%以下")
