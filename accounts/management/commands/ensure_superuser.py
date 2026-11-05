import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("環境変数 DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD の管理者が"
            "いなければ作成します（既にいれば何もしない。初回デプロイ用）")

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME / PASSWORD が未設定のためスキップ")
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"管理者 {username} は既に存在します")
            return
        User.objects.create_superuser(username=username, password=password,
                                      email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""))
        self.stdout.write(self.style.SUCCESS(f"管理者 {username} を作成しました"))
