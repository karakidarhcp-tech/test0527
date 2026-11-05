from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Customer(models.Model):
    name = models.CharField("顧客名", max_length=200, unique=True)
    contact_person = models.CharField("担当者名", max_length=100, blank=True)
    email = models.EmailField("メール", blank=True)
    phone = models.CharField("電話番号", max_length=30, blank=True)
    address = models.CharField("住所", max_length=300, blank=True)
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


class Deal(models.Model):
    class Phase(models.TextChoices):
        LEAD = "lead", "リード"
        PROPOSAL = "proposal", "提案"
        ESTIMATE = "estimate", "見積"
        NEGOTIATION = "negotiation", "交渉"
        WON = "won", "受注"
        LOST = "lost", "失注"

    OPEN_PHASES = [Phase.LEAD, Phase.PROPOSAL, Phase.ESTIMATE, Phase.NEGOTIATION]
    CLOSED_PHASES = [Phase.WON, Phase.LOST]

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
        return self.title

    def get_absolute_url(self):
        return reverse("deal_detail", args=[self.pk])

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
        # 受注/失注になったらクローズ日を自動設定、オープンに戻したらクリア
        if self.phase in self.CLOSED_PHASES:
            if self.closed_date is None:
                self.closed_date = timezone.localdate()
            if self.phase == self.Phase.WON:
                self.probability = 100
            elif self.phase == self.Phase.LOST:
                self.probability = 0
        else:
            self.closed_date = None
        super().save(*args, **kwargs)
