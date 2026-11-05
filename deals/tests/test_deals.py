from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from deals.models import Customer, Deal

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw-123456!")
        self.other = User.objects.create_user("bob", password="pw-123456!")
        self.staff = User.objects.create_user("boss", password="pw-123456!", is_staff=True)
        self.customer = Customer.objects.create(name="テスト商事")
        self.client.login(username="alice", password="pw-123456!")

    def make_deal(self, **kw):
        defaults = dict(title="案件A", customer=self.customer, owner=self.user, amount=1_000_000, probability=50)
        defaults.update(kw)
        return Deal.objects.create(**defaults)


class ModelTests(Base):
    def test_won_sets_probability_and_closed_date(self):
        d = self.make_deal(phase=Deal.Phase.WON)
        self.assertEqual(d.probability, 100)
        self.assertEqual(d.closed_date, timezone.localdate())

    def test_reopen_clears_closed_date(self):
        d = self.make_deal(phase=Deal.Phase.LOST)
        self.assertEqual(d.probability, 0)
        d.phase = Deal.Phase.PROPOSAL
        d.save()
        self.assertIsNone(d.closed_date)

    def test_overdue_and_weighted(self):
        d = self.make_deal(expected_close_date=timezone.localdate() - timedelta(days=1))
        self.assertTrue(d.is_overdue)
        self.assertEqual(d.weighted_amount, 500_000)
        d.phase = Deal.Phase.WON
        d.save()
        self.assertFalse(d.is_overdue)


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for name in ["dashboard", "deal_list", "deal_create", "customer_list", "user_list"]:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, name)
            self.assertIn(reverse("login"), resp["Location"])


class DealViewTests(Base):
    def test_dashboard_aggregates(self):
        self.make_deal(amount=1_000_000, probability=50)
        self.make_deal(amount=2_000_000, probability=10, phase=Deal.Phase.NEGOTIATION)
        self.make_deal(amount=9_000_000, phase=Deal.Phase.WON)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["open_count"], 2)
        self.assertEqual(resp.context["pipeline_total"], 3_000_000)
        self.assertEqual(resp.context["weighted_total"], 700_000)
        self.assertEqual(resp.context["won_month_total"], 9_000_000)
        self.assertEqual(resp.context["win_rate"], 100)

    def test_create_deal_sets_created_by(self):
        resp = self.client.post(reverse("deal_create"), {
            "title": "新規案件", "customer": self.customer.pk, "owner": self.user.pk,
            "phase": "proposal", "amount": 500000, "probability": 30, "expected_close_date": "2026-12-31",
        })
        d = Deal.objects.get(title="新規案件")
        self.assertRedirects(resp, d.get_absolute_url())
        self.assertEqual(d.created_by, self.user)

    def test_probability_validation(self):
        resp = self.client.post(reverse("deal_create"), {
            "title": "x", "customer": self.customer.pk, "phase": "lead", "amount": 0, "probability": 150,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Deal.objects.filter(title="x").exists())

    def test_search_filters(self):
        self.make_deal(title="クラウド移行")
        self.make_deal(title="保守契約", owner=self.other, phase=Deal.Phase.LOST)
        url = reverse("deal_list")
        self.assertEqual(self.client.get(url, {"q": "クラウド"}).context["total_count"], 1)
        self.assertEqual(self.client.get(url, {"q": "テスト商事"}).context["total_count"], 2)
        self.assertEqual(self.client.get(url, {"phase": "open"}).context["total_count"], 1)
        self.assertEqual(self.client.get(url, {"owner": self.other.pk}).context["total_count"], 1)
        resp = self.client.get(url, {"sort": "expected_close_date"})
        self.assertEqual(resp.status_code, 200)

    def test_csv_export(self):
        self.make_deal(title="CSV案件")
        resp = self.client.get(reverse("deal_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV案件", resp.content.decode("utf-8-sig"))

    def test_delete_permission(self):
        d = self.make_deal(owner=self.other, created_by=self.other)
        resp = self.client.post(reverse("deal_delete", args=[d.pk]))
        self.assertEqual(resp.status_code, 403)
        self.client.login(username="boss", password="pw-123456!")
        self.client.post(reverse("deal_delete", args=[d.pk]))
        self.assertFalse(Deal.objects.filter(pk=d.pk).exists())

    def test_customer_with_deals_cannot_be_deleted(self):
        self.make_deal()
        self.client.login(username="boss", password="pw-123456!")
        self.client.post(reverse("customer_delete", args=[self.customer.pk]))
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_all_pages_render(self):
        d = self.make_deal()
        for url in [reverse("deal_detail", args=[d.pk]), reverse("deal_update", args=[d.pk]),
                    reverse("customer_list"), reverse("customer_detail", args=[self.customer.pk]),
                    reverse("customer_create"), reverse("profile"), reverse("password_change")]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
