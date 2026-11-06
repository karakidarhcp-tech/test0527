"""デモデータ（開発・動作確認用）。本番では実行しないこと"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import BillingSchedule, Invoice, InvoiceLine, Payment
from billing.services import accept_quote, create_invoice, default_schedule
from billing.terms import due_date_for
from catalog.models import CompanySettings, Item
from deals.models import Customer, Deal, DealActivity, NumberSequence
from documents.models import IssuedDocument
from documents.services import archive_invoice, archive_quote
from quotes.models import LineMaterial, Quote, QuoteLine

User = get_user_model()

CUSTOMERS = [
    ("株式会社サンプル設計事務所", "御中", 0, 1, 0), ("東和建設株式会社", "御中", 20, 1, 10),
    ("みらいホーム株式会社", "御中", 0, 2, 0), ("北斗インテリア", "御中", 25, 1, 25),
    ("カフェ・グリーンフィールド", "御中", 0, 1, 0), ("青葉クリニック", "御中", 0, 1, 0),
    ("山田 太郎", "様", 0, 0, 0), ("大和ホテルズ株式会社", "御中", 20, 2, 0),
]
TITLES = ["店舗カウンター製作", "壁面収納造作", "キッチン収納", "受付カウンター", "オーダーテーブル",
          "ホテル客室家具", "書斎デスク造作", "カフェ什器一式", "待合ベンチ", "テレビボード製作"]

ITEMS = [
    ("B-001", "board", "シナランバーコア", "21mm 4×8", "枚", "9800"),
    ("B-002", "board", "ポリ合板 白", "4mm 3×6", "枚", "2400"),
    ("B-003", "board", "ナラ突板合板", "4mm 4×8", "枚", "12800"),
    ("M-001", "material", "ナラ無垢材", "30mm 幅広", "才", "1650"),
    ("M-002", "material", "タモ集成材", "25×600×2000", "枚", "18500"),
    ("M-003", "material", "メラミン化粧板", "1.2mm 4×8", "枚", "6800"),
    ("H-001", "hardware", "スライド蝶番", "全かぶせ", "個", "480"),
    ("H-002", "hardware", "スライドレール", "450mm フルオープン", "組", "1850"),
    ("H-003", "hardware", "取手", "真鍮 128mm", "個", "1200"),
    ("H-004", "hardware", "アジャスター", "M10", "個", "180"),
    ("F-001", "finish", "ウレタン塗装", "7分艶", "㎡", "3500"),
    ("F-002", "finish", "オイル仕上げ", "", "㎡", "1800"),
    ("T-001", "transport", "運搬費", "2t車", "台", "25000"),
    ("T-002", "transport", "設置工事", "職人1名", "人工", "28000"),
    ("O-001", "outsource", "ガラス加工", "強化5mm", "㎡", "22000"),
]


class Command(BaseCommand):
    help = "デモ用のユーザー・顧客・品目・案件・見積・請求を作成します（開発環境向け）"

    def add_arguments(self, parser):
        parser.add_argument("--deals", type=int, default=40)
        parser.add_argument("--reset", action="store_true", help="既存の業務データを削除してから作成")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        if opts["reset"]:
            Payment.objects.all().delete()
            BillingSchedule.objects.all().delete()
            InvoiceLine.objects.all().delete()
            Invoice.objects.all().delete()
            Quote.objects.all().delete()
            Deal.objects.filter(parent__isnull=False).delete()
            Deal.objects.all().delete()
            Customer.objects.all().delete()
            Item.objects.all().delete()
            NumberSequence.objects.all().delete()
            IssuedDocument.objects.all().delete()  # QuerySet.delete は開発用リセットのみで使う

        admin = self.user("admin", "管理", "太郎", "admin12345", staff=True)
        users = [admin] + [self.user(u, ln, fn, "demo12345") for u, ln, fn in
                           [("sato", "佐藤", "花子"), ("suzuki", "鈴木", "一郎"), ("tanaka", "田中", "美咲")]]

        s = CompanySettings.load()
        s.company_name, s.postal_code, s.address = "株式会社デモ木工", "123-4567", "東京都デモ区木工町1-2-3"
        s.tel, s.fax, s.email = "03-0000-0000", "03-0000-0001", "info@example.com"
        s.registration_number = "T1234567890123"
        s.bank_info = "デモ銀行 本店営業部 普通 1234567\nカ）デモモツコウ"
        s.save()

        for code, cat, name, spec, unit, cost in ITEMS:
            Item.objects.update_or_create(code=code, defaults=dict(
                category=cat, name=name, spec=spec, unit=unit, cost=Decimal(cost)))
        items = {i.code: i for i in Item.objects.all()}

        customers = []
        for name, hon, close, month, day in CUSTOMERS:
            c, _ = Customer.objects.get_or_create(name=name, defaults=dict(
                honorific=hon, closing_day=close, payment_month_offset=month, payment_day=day,
                contact_person="" if hon == "様" else "ご担当者", address="東京都デモ区1-1"))
            customers.append(c)

        today = timezone.localdate()
        phases = ["lead", "proposal", "estimate", "negotiation", "won", "completed", "lost"]
        for n in range(opts["deals"]):
            phase = random.choices(phases, weights=[2, 3, 4, 2, 4, 2, 1])[0]
            owner = random.choice(users)
            deal = Deal.objects.create(
                title=random.choice(TITLES), customer=random.choice(customers), owner=owner, created_by=admin,
                amount=random.randrange(30, 600) * 10000, probability=random.choice([10, 30, 50, 70]),
                expected_close_date=today + timedelta(days=random.randint(-30, 90)),
                site_address="東京都デモ区2-3-4", description="デモデータ")
            DealActivity.objects.create(deal=deal, user=admin, kind="created", body="案件を作成")
            if phase in ("lead", "proposal"):
                deal.phase = phase
                deal.save()
                continue
            quote = self.make_quote(deal, owner, items)
            if phase in ("estimate", "negotiation"):
                if random.random() < .7:
                    self.issue(quote, owner)
                deal.phase = phase
                deal.save()
                continue
            self.issue(quote, owner)
            if phase == "lost":
                quote.status = Quote.Status.LOST
                quote.save()
                deal.phase = phase
                deal.save()
                continue
            # 受注・完工: 過去 1 年のどこかで受注 → 請求 → 入金
            won_on = today - timedelta(days=random.randint(0, 300))
            sub = quote.totals.subtotal
            month = won_on.replace(day=1)
            rows = default_schedule(sub, month, (won_on + timedelta(days=45)).replace(day=1))
            quote.status = Quote.Status.SUBMITTED
            accept_quote(quote, owner, sub, month, won_on, won_on + timedelta(days=40), rows)
            Deal.objects.filter(pk=deal.pk).update(closed_date=won_on, phase=phase)
            deal.refresh_from_db()
            for sch in deal.billing_schedules.all():
                if sch.billing_month > today.replace(day=1) or random.random() < .15:
                    continue
                inv = create_invoice(deal, owner, sch, use_quote_lines=len(rows) == 1)
                inv.issue_date = max(sch.billing_month, won_on)
                inv.due_date = due_date_for(deal.customer, inv.issue_date)
                inv.save()
                if random.random() < .9:
                    inv.status, inv.issued_at = Invoice.Status.ISSUED, timezone.now()
                    inv.save()
                    archive_invoice(inv, owner)
                    if inv.due_date and inv.due_date < today and random.random() < .85:
                        Payment.objects.create(invoice=inv, date=inv.due_date, amount=inv.totals.total,
                                               created_by=admin)
        self.stdout.write(self.style.SUCCESS(
            f"作成完了: 案件 {Deal.objects.count()} / 見積 {Quote.objects.count()} / 請求書 {Invoice.objects.count()}"
            "\nログイン: admin / admin12345（一般: sato, suzuki, tanaka / demo12345）"))

    def user(self, username, last, first, password, staff=False):
        u, created = User.objects.get_or_create(username=username, defaults=dict(
            last_name=last, first_name=first, is_staff=staff, is_superuser=staff))
        if created:
            u.set_password(password)
            u.save()
        return u

    def make_quote(self, deal, user, items):
        q = Quote.create_for(deal, user)
        q.delivery_terms = "ご発注後 約6週間"
        q.save()
        width = random.choice([1200, 1500, 1800, 2400])
        main = QuoteLine.objects.create(
            quote=q, position=1, name=deal.title.replace("製作", "").replace("造作", "") or deal.title,
            spec=f"W{width}×D{random.choice([450, 600])}×H{random.choice([900, 2100])}",
            quantity=random.choice([1, 1, 2, 3]), unit="台", production_hours=Decimal(random.choice([12, 16, 24, 32])))
        for pos, (code, qty) in enumerate([("B-001", "1.5"), ("B-003", "1"), ("M-001", str(random.randint(3, 12))),
                                           ("H-001", "4"), ("H-002", "2"), ("F-001", "3.2")], start=1):
            it = items[code]
            LineMaterial.objects.create(line=main, position=pos, item=it, name=it.name, spec=it.spec, unit=it.unit,
                                        quantity=Decimal(qty), unit_cost=it.cost)
        main.unit_price = main.suggested_unit_price
        main.save()
        QuoteLine.objects.create(quote=q, position=2, name="運搬・設置費", quantity=1, unit="式",
                                 unit_price=58000, direct_cost=Decimal("41000"))
        return q

    def issue(self, quote, user):
        quote.status, quote.issued_at = Quote.Status.SUBMITTED, timezone.now()
        quote.save()
        archive_quote(quote, user)
