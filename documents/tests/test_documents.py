import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from documents.models import IssuedDocument

User = get_user_model()


def make(number, customer="杢工房", total=110000, date=datetime.date(2026, 11, 6), rev=1, doc_type="invoice"):
    return IssuedDocument.objects.create(
        doc_type=doc_type, number=number, revision=rev, title="件名", customer_name=customer, deal_number="2611001",
        issue_date=date, subtotal=total * 10 // 11, tax=total - total * 10 // 11, total=total, pdf=b"%PDF-1.7 test")


class ArchiveTests(TestCase):
    def test_immutable(self):
        d = make("2611001-B1")
        self.assertEqual(len(d.sha256), 64)
        d.title = "改ざん"
        with self.assertRaises(ValidationError):
            d.save()
        with self.assertRaises(ValidationError):
            d.delete()

    def test_search_by_date_amount_customer(self):
        make("A-B1", customer="杢工房", total=110000, date=datetime.date(2026, 10, 1))
        make("B-B1", customer="北斗製作所", total=550000, date=datetime.date(2026, 11, 15))
        make("C-Q1", customer="北斗製作所", total=33000, date=datetime.date(2026, 11, 20), doc_type="quote")
        self.client.force_login(User.objects.create_user("u", password="pw-123456!"))
        url = reverse("document_list")

        def numbers(params):
            return sorted(d.number for d in self.client.get(url, params).context["page_obj"])
        self.assertEqual(numbers({"customer": "北斗"}), ["B-B1", "C-Q1"])
        self.assertEqual(numbers({"date_from": "2026-11-01", "date_to": "2026-11-16"}), ["B-B1"])
        self.assertEqual(numbers({"amount_min": "100,000", "amount_max": "200000"}), ["A-B1"])
        self.assertEqual(numbers({"doc_type": "quote"}), ["C-Q1"])
        resp = self.client.get(reverse("document_download", args=[IssuedDocument.objects.get(number="A-B1").pk]) + "?download=1")
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])
