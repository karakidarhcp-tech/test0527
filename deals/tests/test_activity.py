from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from deals.models import Customer, Deal, DealActivity
from deals.views import nice_ceiling, nice_scale

User = get_user_model()


class ActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw-123456!")
        self.other = User.objects.create_user("bob", password="pw-123456!")
        self.customer = Customer.objects.create(name="テスト商事")
        self.client.login(username="alice", password="pw-123456!")

    def post_deal(self, url, **overrides):
        data = {"title": "案件A", "customer": self.customer.pk, "owner": self.user.pk, "phase": "proposal",
                "amount": 1000000, "probability": 30, "expected_close_date": "2026-12-01", "description": ""}
        data.update(overrides)
        return self.client.post(url, data)

    def test_create_and_change_are_logged(self):
        self.post_deal(reverse("deal_create"))
        deal = Deal.objects.get()
        self.assertEqual(deal.activities.get().kind, DealActivity.Kind.CREATED)

        self.post_deal(reverse("deal_update", args=[deal.pk]), phase="won", amount=1200000)
        change = deal.activities.filter(kind=DealActivity.Kind.CHANGED).get()
        self.assertIn("フェーズ: 提案 → 受注", change.body)
        self.assertIn("¥1,000,000 → ¥1,200,000", change.body)
        self.assertIn("確度(%): 30% → 100%", change.body)  # 受注による自動設定も記録

    def test_no_change_no_log(self):
        self.post_deal(reverse("deal_create"))
        deal = Deal.objects.get()
        self.post_deal(reverse("deal_update", args=[deal.pk]))
        self.assertFalse(deal.activities.filter(kind=DealActivity.Kind.CHANGED).exists())

    def test_comment_add_and_delete_permission(self):
        deal = Deal.objects.create(title="x", customer=self.customer)
        self.client.post(reverse("deal_add_comment", args=[deal.pk]), {"body": "訪問しました"})
        comment = deal.activities.get(kind=DealActivity.Kind.COMMENT)
        self.assertEqual(comment.user, self.user)
        resp = self.client.get(deal.get_absolute_url())
        self.assertContains(resp, "訪問しました")

        self.client.login(username="bob", password="pw-123456!")
        self.client.post(reverse("activity_delete", args=[comment.pk]))
        self.assertTrue(DealActivity.objects.filter(pk=comment.pk).exists())

        self.client.login(username="alice", password="pw-123456!")
        self.client.post(reverse("activity_delete", args=[comment.pk]))
        self.assertFalse(DealActivity.objects.filter(pk=comment.pk).exists())

    def test_empty_comment_rejected(self):
        deal = Deal.objects.create(title="x", customer=self.customer)
        resp = self.client.post(reverse("deal_add_comment", args=[deal.pk]), {"body": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(deal.activities.exists())


class MonthlyChartTests(TestCase):
    def test_nice_ceiling(self):
        self.assertEqual(nice_ceiling(0), 0)
        self.assertEqual(nice_ceiling(87_000_000), 100_000_000)
        self.assertEqual(nice_ceiling(21_000_000), 25_000_000)
        self.assertEqual(nice_ceiling(1_500_000), 2_000_000)
        self.assertEqual(nice_ceiling(5_000_000), 5_000_000)
        self.assertEqual(nice_scale(42_000_000), (50_000_000, 5))  # 1,000万刻み
        self.assertEqual(nice_scale(15_000_000), (20_000_000, 4))  # 500万刻み

    def test_dashboard_months(self):
        user = User.objects.create_user("alice", password="pw-123456!")
        c = Customer.objects.create(name="c")
        Deal.objects.create(title="a", customer=c, phase="won", amount=3_000_000, closed_date=timezone.localdate())
        Deal.objects.create(title="b", customer=c, phase="won", amount=9_000_000, closed_date=date(2000, 1, 1))
        self.client.force_login(user)
        resp = self.client.get(reverse("dashboard"))
        months = resp.context["months"]
        self.assertEqual(len(months), 12)
        self.assertEqual(months[-1]["total"], 3_000_000)
        self.assertEqual(resp.context["year_total"], 3_000_000)  # 12か月より前は含まない
        self.assertEqual(months[-1]["pct"], 60.0)  # 目盛り上限 5,000,000
        self.assertEqual(resp.context["month_ticks"], [5_000_000, 4_000_000, 3_000_000, 2_000_000, 1_000_000])
