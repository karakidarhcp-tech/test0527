from django.db import transaction
from django.utils import timezone

from catalog.models import CompanySettings
from deals.models import Deal, DealActivity
from deals.numbering import next_document_number
from quotes.models import Quote

from .models import BillingSchedule, Invoice, InvoiceLine
from .terms import due_date_for


def _add_months(d, n):
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)


def default_schedule(amount, start_month, completion_month=None):
    """会社設定の割合（着工金・中間金・残金）で請求予定の初期値を作る。端数は残金で調整"""
    s = CompanySettings.load()
    end = completion_month or _add_months(start_month, 1)
    rows = []
    deposit = amount * s.deposit_percent // 100
    interim = amount * s.interim_percent // 100
    if deposit and deposit < amount:
        rows.append({"label": "着工金", "billing_month": start_month, "amount": deposit})
    if interim and deposit + interim < amount:
        mid = _add_months(start_month, max(1, (end.year - start_month.year) * 12 + end.month - start_month.month) // 2)
        rows.append({"label": "中間金", "billing_month": mid, "amount": interim})
    rest = amount - sum(r["amount"] for r in rows)
    rows.append({"label": "残金" if rows else "一括", "billing_month": end if rows else start_month, "amount": rest})
    return rows


@transaction.atomic
def accept_quote(quote, user, contract_amount, accounting_month, start_date, completion_date, schedules):
    deal = quote.deal
    quote.status = Quote.Status.ACCEPTED
    quote.save(update_fields=["status", "updated_at"])
    deal.phase = Deal.Phase.WON
    deal.contract_amount = contract_amount
    deal.amount = contract_amount  # ダッシュボードの集計（見込み金額）も確定金額に揃える
    deal.accounting_month = accounting_month
    deal.start_date = start_date or deal.start_date
    deal.completion_date = completion_date or deal.completion_date
    deal.save()
    # 未請求の予定は作り直す（請求書を作成済みの予定は残す）
    deal.billing_schedules.filter(invoice__isnull=True).delete()
    start = deal.billing_schedules.count()
    for i, row in enumerate(schedules, start=start + 1):
        BillingSchedule.objects.create(deal=deal, position=i, **row)
    plan = "、".join(f"{r['label']} ¥{r['amount']:,}" for r in schedules)
    DealActivity.objects.create(deal=deal, user=user, kind=DealActivity.Kind.CHANGED,
                                body=f"見積 {quote.number} で受注（確定金額 ¥{contract_amount:,}）\n請求予定: {plan}")


def accepted_quote(deal):
    return deal.quotes.filter(status=Quote.Status.ACCEPTED).order_by("-version").first()


@transaction.atomic
def create_invoice(deal, user, schedule=None, use_quote_lines=False):
    number, _ = next_document_number(deal, "B")
    s = CompanySettings.load()
    today = timezone.localdate()
    title = deal.title + (f"（{schedule.label}）" if schedule and schedule.label not in ("一括",) else "")
    inv = Invoice.objects.create(deal=deal, number=number, title=title, issue_date=today,
                                 due_date=due_date_for(deal.customer, today), notes=s.invoice_terms, created_by=user)
    quote = accepted_quote(deal)
    if use_quote_lines and quote:
        for i, ln in enumerate(quote.lines.all(), start=1):
            InvoiceLine.objects.create(invoice=inv, position=i, name=ln.name, spec=ln.spec, quantity=ln.quantity,
                                       unit=ln.unit, unit_price=ln.unit_price, tax_rate=ln.tax_rate, note=ln.note)
    else:
        amount = schedule.amount if schedule else 0
        label = schedule.label if schedule else ""
        spec = f"御見積 {quote.number} の{label}" if quote and schedule else ""
        InvoiceLine.objects.create(invoice=inv, position=1, name=f"{deal.title} {label}".strip(), spec=spec,
                                   quantity=1, unit="式", unit_price=amount, tax_rate=10)
    if schedule:
        schedule.invoice = inv
        schedule.save(update_fields=["invoice"])
    DealActivity.objects.create(deal=deal, user=user, kind=DealActivity.Kind.CHANGED, body=f"請求書 {number} を作成")
    return inv
