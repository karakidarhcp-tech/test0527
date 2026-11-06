import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from deals.models import Customer, Deal
from deals.numbering import next_deal_number, next_document_number

User = get_user_model()


class NumberingTests(TestCase):
    def setUp(self):
        self.c = Customer.objects.create(name="杢工房")

    def test_monthly_serial_resets_each_month(self):
        self.assertEqual(next_deal_number(datetime.date(2026, 11, 3)), "2611001")
        self.assertEqual(next_deal_number(datetime.date(2026, 11, 30)), "2611002")
        self.assertEqual(next_deal_number(datetime.date(2026, 12, 1)), "2612001")
        self.assertEqual(next_deal_number(datetime.date(2027, 1, 5)), "2701001")

    def test_deal_gets_number_once_and_keeps_it(self):
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2026, 11, 6)):
            d = Deal.objects.create(title="造作棚", customer=self.c)
        self.assertEqual(d.number, "2611001")
        d.title = "造作棚（変更）"
        d.phase = Deal.Phase.WON
        d.save()
        d.refresh_from_db()
        self.assertEqual(d.number, "2611001")

    def test_additional_work_and_document_numbers(self):
        d = Deal.objects.create(title="店舗什器", customer=self.c)
        a1 = Deal.objects.create(title="追加", customer=self.c, parent=d)
        a2 = Deal.objects.create(title="追加", customer=self.c, parent=d)
        self.assertEqual(a1.number, f"{d.number}-A1")
        self.assertEqual(a2.number, f"{d.number}-A2")
        self.assertEqual(next_document_number(d, "Q"), (f"{d.number}-Q1", 1))
        self.assertEqual(next_document_number(d, "Q"), (f"{d.number}-Q2", 2))
        self.assertEqual(next_document_number(a1, "B")[0], f"{d.number}-A1-B1")

    def test_completed_counts_as_won(self):
        d = Deal.objects.create(title="x", customer=self.c, phase=Deal.Phase.COMPLETED)
        self.assertTrue(d.is_won)
        self.assertEqual(d.probability, 100)


class NumberingViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="pw-123456!")
        self.client.force_login(self.user)
        self.c = Customer.objects.create(name="杢工房")

    def test_create_additional_work_from_parent(self):
        parent = Deal.objects.create(title="住宅家具", customer=self.c, site_address="東京都")
        resp = self.client.get(reverse("deal_create") + f"?parent={parent.pk}")
        self.assertContains(resp, f"{parent.number}-A◯")
        self.client.post(reverse("deal_create") + f"?parent={parent.pk}", {
            "title": "住宅家具 追加工事", "customer": self.c.pk, "phase": "estimate", "amount": 0, "probability": 50,
        })
        child = Deal.objects.get(parent=parent)
        self.assertEqual(child.number, f"{parent.number}-A1")

    def test_search_by_number(self):
        d = Deal.objects.create(title="a", customer=self.c)
        Deal.objects.create(title="b", customer=self.c)
        resp = self.client.get(reverse("deal_list"), {"q": d.number})
        self.assertEqual(resp.context["total_count"], 1)

    def test_customer_closing_day_validation(self):
        resp = self.client.post(reverse("customer_create"), {
            "name": "新規", "honorific": "様", "closing_day": 31, "payment_month_offset": 1, "payment_day": 0})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Customer.objects.filter(name="新規").exists())
