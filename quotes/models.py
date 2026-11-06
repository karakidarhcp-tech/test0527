from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from catalog.models import CompanySettings, Item
from catalog.pricing import TAX_RATE_CHOICES, compute_totals, line_amount, margin_rate, price_from_cost
from deals.numbering import next_document_number


class Quote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "下書き"
        SUBMITTED = "submitted", "提出済"
        ACCEPTED = "accepted", "受注"
        LOST = "lost", "失注"

    deal = models.ForeignKey("deals.Deal", verbose_name="案件", on_delete=models.PROTECT, related_name="quotes")
    number = models.CharField("見積番号", max_length=40, unique=True, editable=False)
    version = models.PositiveIntegerField("版", editable=False)
    title = models.CharField("件名", max_length=200)
    issue_date = models.DateField("発行日", default=timezone.localdate)
    valid_until = models.DateField("有効期限", null=True, blank=True)
    status = models.CharField("ステータス", max_length=20, choices=Status.choices, default=Status.DRAFT)
    delivery_terms = models.CharField("納期", max_length=200, blank=True)
    delivery_place = models.CharField("納入場所", max_length=200, blank=True)
    notes = models.TextField("備考（見積書に印字）", blank=True)
    internal_memo = models.TextField("社内メモ（印字しない）", blank=True)
    # 作成時点の設定値を保存（設定を後で変えても過去の見積は変わらない）
    labor_rate = models.PositiveIntegerField("労務単価（円/時間）", default=0)
    target_margin = models.DecimalField("目標粗利率（%）", max_digits=4, decimal_places=1, default=Decimal("30"))
    price_rounding = models.PositiveIntegerField("売価の端数処理", default=100)
    copied_from = models.ForeignKey("self", verbose_name="複製元", null=True, blank=True,
                                    on_delete=models.SET_NULL, editable=False)
    issued_at = models.DateTimeField("発行日時", null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="作成者", null=True, blank=True,
                                   on_delete=models.SET_NULL, editable=False)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "見積"
        verbose_name_plural = "見積"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.number} {self.title}"

    def get_absolute_url(self):
        return reverse("quote_detail", args=[self.pk])

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT

    @classmethod
    def create_for(cls, deal, user=None):
        s = CompanySettings.load()
        today = timezone.localdate()
        with transaction.atomic():
            number, version = next_document_number(deal, "Q")
            return cls.objects.create(
                deal=deal, number=number, version=version, title=deal.title, issue_date=today,
                valid_until=today + timedelta(days=s.quote_valid_days), notes=s.quote_terms,
                delivery_place=deal.site_address, labor_rate=s.labor_rate, target_margin=s.target_margin,
                price_rounding=s.price_rounding, created_by=user,
            )

    def copy_as_new_version(self, user=None):
        """新しい版（-Q{n+1}）として複製する。明細・材料もコピー"""
        with transaction.atomic():
            new = Quote.create_for(self.deal, user)
            for f in ("title", "delivery_terms", "delivery_place", "notes", "internal_memo",
                      "labor_rate", "target_margin", "price_rounding"):
                setattr(new, f, getattr(self, f))
            new.copied_from = self
            new.save()
            for line in self.lines.prefetch_related("materials"):
                materials = list(line.materials.all())
                line.pk = None
                line.quote = new
                line.save()
                for m in materials:
                    m.pk = None
                    m.line = line
                    m.save()
            return new

    # ---- 集計 ----
    def _lines(self):
        cache = getattr(self, "_prefetched_objects_cache", {})
        return list(cache["lines"]) if "lines" in cache else list(self.lines.prefetch_related("materials"))

    @property
    def totals(self):
        return compute_totals((ln.amount, ln.tax_rate) for ln in self._lines())

    @property
    def cost_summary(self):
        lines = self._lines()
        subtotal = sum(ln.amount for ln in lines)
        cost = sum(ln.total_cost for ln in lines)
        return {
            "subtotal": subtotal,
            "material": sum(ln.total_material_cost for ln in lines),
            "labor": sum(ln.total_labor_cost for ln in lines),
            "direct": sum(ln.total_direct_cost for ln in lines),
            "cost": cost,
            "profit": subtotal - cost,
            "margin": margin_rate(subtotal, cost),
            "hours": sum((ln.quantity * ln.production_hours for ln in lines), Decimal("0")),
        }


class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField("並び順", default=0)
    name = models.CharField("品名", max_length=200)
    spec = models.CharField("仕様・寸法", max_length=200, blank=True)
    quantity = models.DecimalField("数量", max_digits=10, decimal_places=2, default=Decimal("1"))
    unit = models.CharField("単位", max_length=20, default="式")
    unit_price = models.BigIntegerField("単価", default=0)
    tax_rate = models.PositiveSmallIntegerField("税率", choices=TAX_RATE_CHOICES, default=10)
    note = models.CharField("備考", max_length=200, blank=True)
    # ---- 原価積算（社内用・1単位あたり） ----
    production_hours = models.DecimalField("見込製作時間（時間/1単位）", max_digits=8, decimal_places=2,
                                           default=Decimal("0"))
    direct_cost = models.DecimalField("その他原価（円/1単位）", max_digits=12, decimal_places=2, default=Decimal("0"),
                                      help_text="外注費・運搬費など材料以外の原価")

    class Meta:
        verbose_name = "見積明細"
        verbose_name_plural = "見積明細"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name

    @property
    def amount(self):
        return line_amount(self.quantity, self.unit_price)

    def _materials(self):
        cache = getattr(self, "_prefetched_objects_cache", {})
        return list(cache["materials"]) if "materials" in cache else list(self.materials.all())

    @property
    def unit_material_cost(self):
        return sum((m.cost for m in self._materials()), Decimal("0"))

    @property
    def unit_labor_cost(self):
        return self.production_hours * self.quote.labor_rate

    @property
    def unit_cost(self):
        return self.unit_material_cost + self.unit_labor_cost + self.direct_cost

    def _times_qty(self, v):
        return line_amount(self.quantity, v)

    @property
    def total_material_cost(self):
        return self._times_qty(self.unit_material_cost)

    @property
    def total_labor_cost(self):
        return self._times_qty(self.unit_labor_cost)

    @property
    def total_direct_cost(self):
        return self._times_qty(self.direct_cost)

    @property
    def total_cost(self):
        return self._times_qty(self.unit_cost)

    @property
    def suggested_unit_price(self):
        if not self.unit_cost:
            return None
        return price_from_cost(self.unit_cost, self.quote.target_margin, self.quote.price_rounding)

    @property
    def margin(self):
        return margin_rate(self.unit_price, self.unit_cost) if self.unit_cost else None


class LineMaterial(models.Model):
    """材料の拾い出し（明細 1 単位あたりの使用量）"""

    line = models.ForeignKey(QuoteLine, on_delete=models.CASCADE, related_name="materials")
    position = models.PositiveIntegerField("並び順", default=0)
    item = models.ForeignKey(Item, verbose_name="品目", null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField("材料名", max_length=200)
    spec = models.CharField("規格", max_length=200, blank=True)
    unit = models.CharField("単位", max_length=20, blank=True)
    quantity = models.DecimalField("使用量", max_digits=10, decimal_places=3, default=Decimal("1"))
    unit_cost = models.DecimalField("原価単価", max_digits=12, decimal_places=2, default=Decimal("0"),
                                    help_text="品目マスタから自動入力（見積作成時点の単価を保存）")

    class Meta:
        verbose_name = "材料"
        verbose_name_plural = "材料"
        ordering = ["position", "id"]

    def __str__(self):
        return self.name

    @property
    def cost(self):
        return self.quantity * self.unit_cost
