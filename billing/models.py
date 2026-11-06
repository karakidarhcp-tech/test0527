from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalog.pricing import TAX_RATE_CHOICES, compute_totals, line_amount


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "下書き"
        ISSUED = "issued", "発行済"

    deal = models.ForeignKey("deals.Deal", verbose_name="案件", on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField("請求書番号", max_length=40, unique=True, editable=False)
    title = models.CharField("件名", max_length=200)
    issue_date = models.DateField("請求日", default=timezone.localdate)
    due_date = models.DateField("お支払期限", null=True, blank=True)
    status = models.CharField("状態", max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField("備考（請求書に印字）", blank=True)
    issued_at = models.DateTimeField("発行日時", null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="作成者", null=True, blank=True,
                                   on_delete=models.SET_NULL, editable=False)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "請求書"
        verbose_name_plural = "請求書"
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return f"{self.number} {self.title}"

    def get_absolute_url(self):
        return reverse("invoice_detail", args=[self.pk])

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT

    def _cached(self, name, qs):
        cache = getattr(self, "_prefetched_objects_cache", {})
        return list(cache[name]) if name in cache else list(qs)

    @property
    def totals(self):
        return compute_totals((ln.amount, ln.tax_rate) for ln in self._cached("lines", self.lines.all()))

    @property
    def paid_amount(self):
        return sum(p.amount for p in self._cached("payments", self.payments.all()))

    @property
    def balance(self):
        return self.totals.total - self.paid_amount

    @property
    def payment_status(self):
        """(key, 表示名)"""
        if self.status == self.Status.DRAFT:
            return "draft", "下書き"
        paid, total = self.paid_amount, self.totals.total
        if paid >= total:
            return "paid", "入金済"
        if paid > 0:
            return "partial", "一部入金"
        if self.due_date and self.due_date < timezone.localdate():
            return "overdue", "期限超過"
        return "unpaid", "未入金"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField("並び順", default=0)
    name = models.CharField("品名", max_length=200)
    spec = models.CharField("仕様・寸法", max_length=200, blank=True)
    quantity = models.DecimalField("数量", max_digits=10, decimal_places=2, default=1)
    unit = models.CharField("単位", max_length=20, default="式")
    unit_price = models.BigIntegerField("単価", default=0)
    tax_rate = models.PositiveSmallIntegerField("税率", choices=TAX_RATE_CHOICES, default=10)
    note = models.CharField("備考", max_length=200, blank=True)

    class Meta:
        verbose_name = "請求明細"
        verbose_name_plural = "請求明細"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name

    @property
    def amount(self):
        return line_amount(self.quantity, self.unit_price)


class BillingSchedule(models.Model):
    """分割請求の予定（着工金・中間金・残金など）。金額は税抜"""

    deal = models.ForeignKey("deals.Deal", verbose_name="案件", on_delete=models.CASCADE,
                             related_name="billing_schedules")
    position = models.PositiveIntegerField("並び順", default=0)
    label = models.CharField("区分", max_length=50)
    billing_month = models.DateField("請求月", help_text="月の1日で保存")
    amount = models.BigIntegerField("金額（税抜）")
    invoice = models.OneToOneField(Invoice, verbose_name="請求書", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="schedule")

    class Meta:
        verbose_name = "分割請求"
        verbose_name_plural = "分割請求"
        ordering = ["position", "billing_month", "id"]

    def __str__(self):
        return f"{self.deal.number} {self.label}"

    def save(self, *args, **kwargs):
        self.billing_month = self.billing_month.replace(day=1)
        super().save(*args, **kwargs)

    @property
    def status(self):
        """(key, 表示名)"""
        if not self.invoice_id:
            if self.billing_month <= timezone.localdate().replace(day=1):
                return "due", "請求月です"
            return "planned", "予定"
        return self.invoice.payment_status


class Payment(models.Model):
    class Method(models.TextChoices):
        TRANSFER = "transfer", "振込"
        CASH = "cash", "現金"
        OFFSET = "offset", "相殺"
        OTHER = "other", "その他"

    invoice = models.ForeignKey(Invoice, verbose_name="請求書", on_delete=models.PROTECT, related_name="payments")
    date = models.DateField("入金日", default=timezone.localdate)
    amount = models.BigIntegerField("入金額（税込）")
    method = models.CharField("方法", max_length=20, choices=Method.choices, default=Method.TRANSFER)
    note = models.CharField("メモ", max_length=200, blank=True, help_text="振込手数料の差引など")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="登録者", null=True, blank=True,
                                   on_delete=models.SET_NULL, editable=False)
    created_at = models.DateTimeField("登録日時", auto_now_add=True)

    class Meta:
        verbose_name = "入金"
        verbose_name_plural = "入金"
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.invoice.number} {self.date} ¥{self.amount:,}"


def deal_billing_status(deal):
    """案件の請求状況（請求・入金データから自動計算）。(key, 表示名)"""
    if not deal.is_won:
        return "none", "金額未確定"
    invoices = [i for i in deal.invoices.all() if i.status == Invoice.Status.ISSUED]
    if not invoices:
        return "unbilled", "未請求"
    billed = sum(i.totals.subtotal for i in invoices)
    total = sum(i.totals.total for i in invoices)
    paid = sum(i.paid_amount for i in invoices)
    fully_billed = deal.contract_amount is None or billed >= deal.contract_amount
    if paid >= total:
        return ("paid", "入金済") if fully_billed else ("partial_billed", "一部請求済（入金済）")
    if paid > 0:
        return "partial_paid", "一部入金"
    return ("billed", "請求済") if fully_billed else ("partial_billed", "一部請求済")
