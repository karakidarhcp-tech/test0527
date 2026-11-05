import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from deals.models import Customer, Deal

User = get_user_model()

CUSTOMERS = ["株式会社サンプル商事", "東和システム株式会社", "みらい物流株式会社", "北斗製作所",
             "株式会社グリーンフィールド", "青葉メディカル", "株式会社ひかり建設", "大和フーズ株式会社"]
TITLES = ["基幹システム刷新", "Webサイトリニューアル", "保守契約更新", "クラウド移行支援", "業務改善コンサル",
          "社内ポータル構築", "セキュリティ診断", "データ分析基盤導入", "モバイルアプリ開発", "ヘルプデスク委託"]


class Command(BaseCommand):
    help = "デモ用のユーザー・顧客・案件を作成します(開発環境向け)"

    def add_arguments(self, parser):
        parser.add_argument("--deals", type=int, default=40)

    def handle(self, *args, **opts):
        random.seed(42)
        admin, created = User.objects.get_or_create(
            username="admin", defaults={"is_staff": True, "is_superuser": True,
                                        "last_name": "管理", "first_name": "太郎"})
        if created:
            admin.set_password("admin12345")
            admin.save()
        users = [admin]
        for uname, last, first in [("sato", "佐藤", "花子"), ("suzuki", "鈴木", "一郎"), ("tanaka", "田中", "美咲")]:
            u, created = User.objects.get_or_create(username=uname, defaults={"last_name": last, "first_name": first})
            if created:
                u.set_password("demo12345")
                u.save()
            users.append(u)

        customers = [Customer.objects.get_or_create(name=n, defaults={"contact_person": "ご担当者"})[0]
                     for n in CUSTOMERS]
        today = timezone.localdate()
        phases = [p for p, _ in Deal.Phase.choices]
        for i in range(opts["deals"]):
            phase = random.choices(phases, weights=[3, 3, 3, 2, 2, 1])[0]
            Deal.objects.create(
                title=f"{random.choice(TITLES)} {i + 1:03d}",
                customer=random.choice(customers),
                owner=random.choice(users),
                created_by=admin,
                phase=phase,
                amount=random.randrange(50, 3000) * 10000,
                probability={"lead": 10, "proposal": 30, "estimate": 50, "negotiation": 70}.get(phase, 0),
                expected_close_date=today + timedelta(days=random.randint(-30, 90)),
                description="デモデータ",
            )
        self.stdout.write(self.style.SUCCESS(
            f"作成完了: 案件 {opts['deals']}件 / ログイン admin / admin12345（一般: sato, suzuki, tanaka / demo12345）"))
