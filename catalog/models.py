from decimal import Decimal

from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.urls import reverse


class Item(models.Model):
    """品目・原価マスタ（Excel 原価表から取り込み可能）"""

    class Category(models.TextChoices):
        MATERIAL = "material", "材料"
        BOARD = "board", "板材・合板"
        HARDWARE = "hardware", "金物・部品"
        FINISH = "finish", "塗装・仕上"
        OUTSOURCE = "outsource", "外注"
        TRANSPORT = "transport", "運搬・設置"
        OTHER = "other", "その他"

    code = models.CharField("品番", max_length=50, blank=True)
    category = models.CharField("分類", max_length=20, choices=Category.choices, default=Category.MATERIAL)
    name = models.CharField("品名", max_length=200)
    spec = models.CharField("規格・仕様", max_length=200, blank=True)
    unit = models.CharField("単位", max_length=20, default="個")
    cost = models.DecimalField("原価単価", max_digits=12, decimal_places=2, default=Decimal("0"))
    price = models.PositiveIntegerField("標準売価", null=True, blank=True, help_text="空欄なら原価と目標粗利率から計算")
    is_active = models.BooleanField("使用中", default=True)
    notes = models.CharField("備考", max_length=300, blank=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "品目"
        verbose_name_plural = "品目"
        ordering = ["category", "code", "name"]
        constraints = [
            models.UniqueConstraint(fields=["code"], condition=~models.Q(code=""), name="unique_item_code"),
        ]

    def __str__(self):
        label = f"{self.name} {self.spec}".strip()
        return f"[{self.code}] {label}" if self.code else label

    def get_absolute_url(self):
        return reverse("item_update", args=[self.pk])


def default_registration_validator():
    return RegexValidator(r"^(T\d{13})?$", "登録番号は T + 13桁の数字で入力してください（例: T1234567890123）")


class CompanySettings(models.Model):
    """会社情報・見積と請求の既定値（1 行だけ使う）"""

    company_name = models.CharField("会社名", max_length=200, default="（会社名を設定してください）")
    postal_code = models.CharField("郵便番号", max_length=10, blank=True)
    address = models.CharField("住所", max_length=300, blank=True)
    tel = models.CharField("電話番号", max_length=30, blank=True)
    fax = models.CharField("FAX", max_length=30, blank=True)
    email = models.EmailField("メール", blank=True)
    registration_number = models.CharField(
        "適格請求書発行事業者 登録番号", max_length=14, blank=True, validators=[default_registration_validator()])
    bank_info = models.TextField("振込先", blank=True, help_text="例: ◯◯銀行 ◯◯支店 普通 1234567 カ）◯◯")

    quote_valid_days = models.PositiveSmallIntegerField("見積有効期限（日数）", default=30)
    quote_terms = models.TextField("見積書の既定の備考", blank=True, default="お支払条件: 別途ご相談\n納期: ご発注後 別途ご相談")
    invoice_terms = models.TextField("請求書の既定の備考", blank=True, default="お振込手数料は貴社にてご負担願います。")

    labor_rate = models.PositiveIntegerField("労務単価（円/時間）", default=4000, help_text="見込製作時間 × 労務単価 を原価に加算")
    target_margin = models.DecimalField(
        "目標粗利率（%）", max_digits=4, decimal_places=1, default=Decimal("30.0"),
        validators=[MaxValueValidator(Decimal("95"))], help_text="売価 = 原価 ÷ (1 − 粗利率)")
    price_rounding = models.PositiveIntegerField(
        "売価の端数処理", default=100, choices=[(1, "1円単位"), (10, "10円単位"), (100, "100円単位"), (1000, "1,000円単位")])

    deposit_percent = models.PositiveSmallIntegerField("着工金の割合（%）", default=50, validators=[MaxValueValidator(100)])
    interim_percent = models.PositiveSmallIntegerField(
        "中間金の割合（%）", default=0, validators=[MaxValueValidator(100)], help_text="残りが残金になります")

    class Meta:
        verbose_name = "会社設定"
        verbose_name_plural = "会社設定"

    def __str__(self):
        return self.company_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
