from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Customer(models.Model):
    name = models.CharField("顧客名", max_length=200, unique=True)
    contact_person = models.CharField("担当者名", max_length=100, blank=True)
    email = models.EmailField("メール", blank=True)
    phone = models.CharField("電話番号", max_length=30, blank=True)
    postal_code = models.CharField("郵便番号", max_length=10, blank=True)
    address = models.CharField("住所", max_length=300, blank=True)
    honorific = models.CharField("敬称", max_length=10, default="御中",
                                 choices=[("御中", "御中"), ("様", "様"), ("殿", "殿")])
    closing_day = models.PositiveSmallIntegerField(
        "締め日", default=0, help_text="1〜28 の日付。0 は末日締め")
    payment_month_offset = models.PositiveSmallIntegerField(
        "支払月", default=1, choices=[(0, "当月"), (1, "翌月"), (2, "翌々月"), (3, "3か月後")])
    payment_day = models.PositiveSmallIntegerField(
        "支払日", default=0, help_text="1〜28 の日付。0 は末日払い")
    notes = models.TextField("備考", blank=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "顧客"
        verbose_name_plural = "顧客"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("customer_detail", args=[self.pk])

    @property
    def name_with_honorific(self):
        return f"{self.name} {self.honorific}"

    @property
    def payment_terms_display(self):
        close = "末日" if self.closing_day == 0 else f"{self.closing_day}日"
        pay = "末日" if self.payment_day == 0 else f"{self.payment_day}日"
        return f"{close}締め {self.get_payment_month_offset_display()}{pay}払い"


class Deal(models.Model):
    class Phase(models.TextChoices):
        LEAD = "lead", "リード"
        PROPOSAL = "proposal", "提案"
        ESTIMATE = "estimate", "見積"
        NEGOTIATION = "negotiation", "交渉"
        WON = "won", "受注"
        COMPLETED = "completed", "完工"
        LOST = "lost", "失注"

    OPEN_PHASES = [Phase.LEAD, Phase.PROPOSAL, Phase.ESTIMATE, Phase.NEGOTIATION]
    WON_PHASES = [Phase.WON, Phase.COMPLETED]
    CLOSED_PHASES = [Phase.WON, Phase.COMPLETED, Phase.LOST]

    number = models.CharField("案件番号", max_length=30, unique=True, editable=False)
    parent = models.ForeignKey(
        "self", verbose_name="元案件（追加工事の場合）", on_delete=models.PROTECT,
        null=True, blank=True, related_name="children", editable=False,
    )
    title = models.CharField("案件名", max_length=200)
    customer = models.ForeignKey(
        Customer, verbose_name="顧客", on_delete=models.PROTECT, related_name="deals"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="担当者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_deals",
    )
    phase = models.CharField("フェーズ", max_length=20, choices=Phase.choices, default=Phase.LEAD)
    amount = models.PositiveBigIntegerField("見込み金額(円)", default=0)
    probability = models.PositiveSmallIntegerField("確度(%)", default=10)
    expected_close_date = models.DateField("受注予定日", null=True, blank=True)
    closed_date = models.DateField("クローズ日", null=True, blank=True)
    contract_amount = models.PositiveBigIntegerField(
        "確定金額(税抜)", null=True, blank=True, help_text="受注時に見積から自動設定。手動で変更も可")
    accounting_month = models.DateField("計上月", null=True, blank=True, help_text="月の1日で保存")
    start_date = models.DateField("着工予定日", null=True, blank=True)
    completion_date = models.DateField("完工予定日", null=True, blank=True)
    site_address = models.CharField("現場住所", max_length=300, blank=True)
    description = models.TextField("内容・メモ", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="作成者",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_deals",
        editable=False,
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "案件"
        verbose_name_plural = "案件"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.number} {self.title}" if self.number else self.title

    def get_absolute_url(self):
        return reverse("deal_detail", args=[self.pk])

    @property
    def is_won(self):
        return self.phase in self.WON_PHASES

    @property
    def billing_base_amount(self):
        """請求の基準額（税抜）: 確定金額、なければ見込み金額"""
        return self.contract_amount if self.contract_amount is not None else self.amount

    @property
    def is_open(self):
        return self.phase in self.OPEN_PHASES

    @property
    def is_overdue(self):
        return (
            self.is_open
            and self.expected_close_date is not None
            and self.expected_close_date < timezone.localdate()
        )

    @property
    def weighted_amount(self):
        return self.amount * self.probability // 100

    def save(self, *args, **kwargs):
        if not self.number:
            from .numbering import next_child_number, next_deal_number
            self.number = next_child_number(self.parent) if self.parent_id else next_deal_number()
        if self.accounting_month:
            self.accounting_month = self.accounting_month.replace(day=1)
        # 受注/完工/失注になったらクローズ日を自動設定、オープンに戻したらクリア
        if self.phase in self.CLOSED_PHASES:
            if self.closed_date is None:
                self.closed_date = timezone.localdate()
            if self.phase in self.WON_PHASES:
                self.probability = 100
            elif self.phase == self.Phase.LOST:
                self.probability = 0
        else:
            self.closed_date = None
        super().save(*args, **kwargs)


class DealActivity(models.Model):
    """案件の活動履歴（コメント・変更履歴）"""

    class Kind(models.TextChoices):
        CREATED = "created", "作成"
        CHANGED = "changed", "変更"
        COMMENT = "comment", "コメント"

    deal = models.ForeignKey(Deal, verbose_name="案件", on_delete=models.CASCADE, related_name="activities")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ユーザー", on_delete=models.SET_NULL, null=True, blank=True
    )
    kind = models.CharField("種別", max_length=20, choices=Kind.choices)
    body = models.TextField("内容")
    created_at = models.DateTimeField("日時", auto_now_add=True)

    class Meta:
        verbose_name = "活動履歴"
        verbose_name_plural = "活動履歴"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.deal} / {self.get_kind_display()}"


class NumberSequence(models.Model):
    """採番カウンタ。key 例: "2611"（案件の月内連番）, "2611001-A"（追加工事）, "2611001-Q"（見積の版）"""
    key = models.CharField("キー", max_length=40, unique=True)
    last = models.PositiveIntegerField("最終番号", default=0)

    class Meta:
        verbose_name = "採番カウンタ"
        verbose_name_plural = "採番カウンタ"

    def __str__(self):
        return f"{self.key}: {self.last}"
