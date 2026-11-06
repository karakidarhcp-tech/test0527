import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from billing.models import BillingSchedule, Invoice, Payment, deal_billing_status
from billing.terms import due_date_for
from catalog.models import CompanySettings
from deals.models import Customer, Deal
from documents.models import IssuedDocument
from quotes.models import Quote, QuoteLine

User = get_user_model()


class Terms:
    def __init__(self, closing_day, payment_month_offset, payment_day):
        self.closing_day, self.payment_month_offset, self.payment_day = closing_day, payment_month_offset, payment_day


class DueDateTests(SimpleTestCase):
    def test_end_of_month_close_next_month_end(self):
        self.assertEqual(due_date_for(Terms(0, 1, 0), datetime.date(2026, 11, 6)), datetime.date(2026, 12, 31))
        self.assertEqual(due_date_for(Terms(0, 1, 0), datetime.date(2027, 1, 31)), datetime.date(2027, 2, 28))

    def test_20th_close(self):
        c = Terms(20, 1, 10)
        self.assertEqual(due_date_for(c, datetime.date(2026, 11, 20)), datetime.date(2026, 12, 10))
        self.assertEqual(due_date_for(c, datetime.date(2026, 11, 21)), datetime.date(2027, 1, 10))
        self.assertEqual(due_date_for(Terms(20, 2, 0), datetime.date(2026, 12, 25)), datetime.date(2027, 3, 31))


class BillingFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="pw-123456!")
        self.staff = User.objects.create_user("boss", password="pw-123456!", is_staff=True)
        self.client.force_login(self.user)
        s = CompanySettings.load()
        s.deposit_percent, s.interim_percent = 50, 0
        s.save()
        self.customer = Customer.objects.create(name="杢工房", closing_day=0, payment_month_offset=1, payment_day=0)
        self.deal = Deal.objects.create(title="店舗什器", customer=self.customer)
        self.quote = Quote.create_for(self.deal, self.user)
        QuoteLine.objects.create(quote=self.quote, name="カウンター", quantity=1, unit_price=600000)
        QuoteLine.objects.create(quote=self.quote, name="棚", quantity=2, unit_price=200001)
        self.client.post(reverse("quote_issue", args=[self.quote.pk]))  # 税抜 1,000,002

    def accept(self, rows, contract=1000002):
        data = {"contract_amount": contract, "accounting_month": "2026-11", "start_date": "2026-11-10",
                "completion_date": "2026-12-20", "sch-TOTAL_FORMS": len(rows), "sch-INITIAL_FORMS": 0,
                "sch-MIN_NUM_FORMS": 0, "sch-MAX_NUM_FORMS": 1000}
        for i, (label, month, amount) in enumerate(rows):
            data.update({f"sch-{i}-label": label, f"sch-{i}-billing_month": month, f"sch-{i}-amount": amount})
        return self.client.post(reverse("quote_accept", args=[self.quote.pk]), data)

    def test_accept_form_proposes_default_split(self):
        resp = self.client.get(reverse("quote_accept", args=[self.quote.pk]))
        initial = resp.context["formset"].initial
        self.assertEqual([(r["label"], r["amount"]) for r in initial], [("着工金", 500001), ("残金", 500001)])

    def test_accept_requires_schedule_to_match_contract(self):
        resp = self.accept([("着工金", "2026-11", 500000), ("残金", "2026-12", 500000)])
        self.assertContains(resp, "一致しません")
        self.assertFalse(BillingSchedule.objects.exists())

    def test_full_flow_accept_invoice_pay(self):
        self.assertEqual(self.accept([("着工金", "2026-11", 500000), ("残金", "2026-12", 500002)]).status_code, 302)
        self.deal.refresh_from_db()
        self.quote.refresh_from_db()
        self.assertEqual((self.deal.phase, self.deal.contract_amount, self.deal.amount), (Deal.Phase.WON, 1000002, 1000002))
        self.assertEqual(self.deal.accounting_month, datetime.date(2026, 11, 1))
        self.assertEqual(self.quote.status, Quote.Status.ACCEPTED)
        self.assertEqual(deal_billing_status(self.deal)[1], "未請求")

        deposit, rest = self.deal.billing_schedules.all()
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": deposit.pk, "mode": "lump"})
        inv = Invoice.objects.get()
        self.assertEqual(inv.number, f"{self.deal.number}-B1")
        self.assertEqual((inv.totals.subtotal, inv.totals.tax, inv.totals.total), (500000, 50000, 550000))
        self.assertIn("着工金", inv.lines.get().name)
        deposit.refresh_from_db()
        self.assertEqual(deposit.invoice, inv)
        # 同じ予定から二重に作らない
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": deposit.pk})
        self.assertEqual(Invoice.objects.count(), 1)

        self.client.post(reverse("invoice_issue", args=[inv.pk]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.Status.ISSUED)
        self.assertTrue(IssuedDocument.objects.filter(number=inv.number, doc_type="invoice").exists())
        self.assertEqual(deal_billing_status(self.deal)[1], "一部請求済")

        self.client.post(reverse("payment_add", args=[inv.pk]), {"date": "2026-11-30", "amount": 549340, "method": "transfer", "note": "手数料差引"})
        self.assertEqual(Invoice.objects.get().payment_status[1], "一部入金")
        self.client.post(reverse("payment_add", args=[inv.pk]), {"date": "2026-12-01", "amount": 660, "method": "offset"})
        self.assertEqual(Invoice.objects.get().payment_status[1], "入金済")

        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": rest.pk})
        inv2 = Invoice.objects.latest("id")
        self.assertEqual(inv2.number, f"{self.deal.number}-B2")
        self.client.post(reverse("invoice_issue", args=[inv2.pk]))
        self.assertEqual(deal_billing_status(self.deal)[1], "一部入金")  # 全額請求済み・一部入金
        self.client.post(reverse("payment_add", args=[inv2.pk]), {"date": "2027-01-31", "amount": inv2.totals.total, "method": "transfer"})
        self.assertEqual(deal_billing_status(self.deal)[1], "入金済")
        # 画面
        for url in [reverse("invoice_list") + f"?tab={t}" for t in ("todo", "draft", "unpaid", "overdue", "paid", "all")] + [
                self.deal.get_absolute_url(), inv.get_absolute_url(), reverse("document_list")]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_invoice_from_quote_lines(self):
        self.accept([("一括", "2026-12", 1000002)])
        sch = self.deal.billing_schedules.get()
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": sch.pk, "mode": "lines"})
        inv = Invoice.objects.get()
        self.assertEqual([ln.name for ln in inv.lines.all()], ["カウンター", "棚"])
        self.assertEqual(inv.totals.subtotal, 1000002)
        self.assertEqual(inv.due_date.day in (28, 29, 30, 31), True)

    def test_issued_invoice_locked_and_revert_keeps_archive(self):
        self.accept([("一括", "2026-12", 1000002)])
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": self.deal.billing_schedules.get().pk})
        inv = Invoice.objects.get()
        self.client.post(reverse("invoice_issue", args=[inv.pk]))
        self.assertRedirects(self.client.get(reverse("invoice_edit", args=[inv.pk])), inv.get_absolute_url())
        self.assertEqual(self.client.post(reverse("invoice_revert", args=[inv.pk]), {"reason": "x"}).status_code, 403)
        self.client.force_login(self.staff)
        self.client.post(reverse("invoice_revert", args=[inv.pk]), {"reason": ""})
        self.assertEqual(Invoice.objects.get().status, "issued")  # 理由必須
        self.client.post(reverse("invoice_revert", args=[inv.pk]), {"reason": "単価の誤り"})
        self.assertEqual(Invoice.objects.get().status, "draft")
        self.client.post(reverse("invoice_delete", args=[inv.pk]))
        self.assertTrue(Invoice.objects.filter(pk=inv.pk).exists())  # 発行歴があるので削除不可
        self.client.post(reverse("invoice_issue", args=[inv.pk]))
        self.assertEqual(list(IssuedDocument.objects.filter(number=inv.number).values_list("revision", flat=True)
                              .order_by("revision")), [1, 2])

    def test_changing_issue_date_recomputes_due_date(self):
        self.accept([("一括", "2026-12", 1000002)])
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": self.deal.billing_schedules.get().pk})
        inv = Invoice.objects.get()
        line = inv.lines.get()
        data = {"title": inv.title, "issue_date": "2027-01-15", "due_date": inv.due_date.isoformat(), "notes": "",
                "lines-TOTAL_FORMS": 1, "lines-INITIAL_FORMS": 1, "lines-MIN_NUM_FORMS": 0, "lines-MAX_NUM_FORMS": 1000,
                "lines-0-id": line.pk, "lines-0-invoice": inv.pk, "lines-0-name": line.name, "lines-0-spec": "",
                "lines-0-quantity": "1", "lines-0-unit": "式", "lines-0-unit_price": line.unit_price,
                "lines-0-tax_rate": "10", "lines-0-note": ""}
        self.client.post(reverse("invoice_edit", args=[inv.pk]), data)
        self.assertEqual(Invoice.objects.get().due_date, datetime.date(2027, 2, 28))  # 末日締め翌月末払い
        data.update({"issue_date": "2027-03-01", "due_date": "2027-03-10"})  # 期限を手で指定したら尊重
        self.client.post(reverse("invoice_edit", args=[inv.pk]), data)
        self.assertEqual(Invoice.objects.get().due_date, datetime.date(2027, 3, 10))

    def test_payment_rules(self):
        self.accept([("一括", "2026-12", 1000002)])
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": self.deal.billing_schedules.get().pk})
        inv = Invoice.objects.get()
        self.client.post(reverse("payment_add", args=[inv.pk]), {"date": "2026-12-01", "amount": 100, "method": "cash"})
        self.assertFalse(Payment.objects.exists())  # 発行前は登録不可
        self.client.post(reverse("invoice_issue", args=[inv.pk]))
        self.client.post(reverse("payment_add", args=[inv.pk]), {"date": "2026-12-01", "amount": 0, "method": "cash"})
        self.assertFalse(Payment.objects.exists())
        self.client.post(reverse("payment_add", args=[inv.pk]), {"date": "2026-12-01", "amount": 1000, "method": "cash"})
        p = Payment.objects.get()
        other = User.objects.create_user("other", password="pw-123456!")
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("payment_delete", args=[p.pk])).status_code, 403)
        self.client.force_login(self.staff)
        self.client.post(reverse("invoice_revert", args=[inv.pk]), {"reason": "x"})
        self.assertEqual(Invoice.objects.get().status, "issued")  # 入金ありは戻せない

    def test_overdue_listed(self):
        self.accept([("一括", "2026-11", 1000002)])
        self.client.post(reverse("invoice_create", args=[self.deal.pk]), {"schedule": self.deal.billing_schedules.get().pk})
        inv = Invoice.objects.get()
        Invoice.objects.filter(pk=inv.pk).update(issue_date=datetime.date(2020, 1, 1), due_date=datetime.date(2020, 2, 29))
        self.client.post(reverse("invoice_issue", args=[inv.pk]))
        resp = self.client.get(reverse("invoice_list") + "?tab=overdue")
        self.assertContains(resp, inv.number)
        self.assertEqual(Invoice.objects.get().payment_status[1], "期限超過")
