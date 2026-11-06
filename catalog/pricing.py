"""金額・消費税の計算（インボイス制度対応）

ルール（CLAUDE.md「金額・税の計算」）:
- 金額は整数（円）、数量は Decimal
- 明細金額 = 数量 × 単価 を四捨五入
- 消費税は書類ごと・税率ごとに 1 回だけ計算し、切り捨て
"""
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP, Decimal

TAX_RATE_CHOICES = [(10, "10%"), (8, "8%（軽減）"), (0, "非課税・対象外")]


def to_decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def line_amount(quantity, unit_price):
    """明細金額（円）= 数量 × 単価、四捨五入"""
    return int((to_decimal(quantity) * to_decimal(unit_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass
class TaxBucket:
    rate: int
    base: int = 0  # 税抜対象額

    @property
    def tax(self):
        return int((Decimal(self.base) * self.rate / 100).quantize(Decimal("1"), rounding=ROUND_DOWN))


@dataclass
class Totals:
    buckets: "OrderedDict[int, TaxBucket]" = field(default_factory=OrderedDict)

    @property
    def subtotal(self):
        return sum(b.base for b in self.buckets.values())

    @property
    def tax(self):
        return sum(b.tax for b in self.buckets.values())

    @property
    def total(self):
        return self.subtotal + self.tax

    @property
    def rows(self):
        """税率の高い順の内訳（帳票用）"""
        return [self.buckets[r] for r in sorted(self.buckets, reverse=True)]


def compute_totals(lines):
    """lines: (金額, 税率) の並び。税率ごとに集計して 1 回だけ消費税を計算する"""
    totals = Totals()
    for amount, rate in lines:
        totals.buckets.setdefault(rate, TaxBucket(rate)).base += int(amount)
    return totals


def round_up_to(value, unit):
    """unit 円単位に切り上げ（売価の端数処理）"""
    unit = int(unit or 1)
    return int((to_decimal(value) / unit).quantize(Decimal("1"), rounding=ROUND_CEILING)) * unit


def price_from_cost(cost, margin_percent, rounding=1):
    """原価と目標粗利率から売価を計算: 売価 = 原価 ÷ (1 − 粗利率)、rounding 円単位で切り上げ"""
    margin = to_decimal(margin_percent)
    if margin >= 100:
        raise ValueError("粗利率は100%未満にしてください")
    return round_up_to(to_decimal(cost) / (1 - margin / 100), rounding)


def margin_rate(price, cost):
    """粗利率（%）。売価 0 なら None"""
    price = to_decimal(price)
    if price == 0:
        return None
    return float(((price - to_decimal(cost)) / price * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
