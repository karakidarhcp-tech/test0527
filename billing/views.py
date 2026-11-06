from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from deals.models import Deal, DealActivity
from quotes.models import Quote
from quotes.views import _save_positions

from .forms import AcceptForm, InvoiceForm, InvoiceLineFormSet, PaymentForm, ScheduleFormSet
from .models import BillingSchedule, Invoice, Payment
from .services import accept_quote, create_invoice, default_schedule


def log(deal, user, body):
    DealActivity.objects.create(deal=deal, user=user, kind=DealActivity.Kind.CHANGED, body=body)


@login_required
def quote_accept(request, pk):
    quote = get_object_or_404(Quote.objects.select_related("deal", "deal__customer"), pk=pk)
    deal = quote.deal
    if quote.status != Quote.Status.SUBMITTED:
        messages.error(request, "発行（提出）済みの見積だけ受注にできます。")
        return redirect(quote)
    if deal.billing_schedules.filter(invoice__isnull=False).exists():
        messages.warning(request, "この案件には請求書作成済みの予定があります。それ以外の予定を作り直します。")
    subtotal = quote.totals.subtotal
    this_month = timezone.localdate().replace(day=1)
    initial = {"contract_amount": subtotal, "accounting_month": deal.accounting_month or this_month,
               "start_date": deal.start_date, "completion_date": deal.completion_date}
    form = AcceptForm(request.POST or None, initial=initial)
    contract = None
    if request.method == "POST" and form.is_valid():
        contract = form.cleaned_data["contract_amount"]
    completion = deal.completion_date.replace(day=1) if deal.completion_date else None
    formset = ScheduleFormSet(request.POST or None, prefix="sch", contract_amount=contract,
                              initial=None if request.method == "POST"
                              else default_schedule(subtotal, this_month, completion))
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        rows = [f.cleaned_data for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        for r in rows:
            r.pop("DELETE", None)
        cd = form.cleaned_data
        accept_quote(quote, request.user, cd["contract_amount"], cd["accounting_month"], cd["start_date"],
                     cd["completion_date"], rows)
        messages.success(request, f"受注にしました。請求予定を {len(rows)} 件作成しました。")
        return redirect(deal.get_absolute_url() + "#billing")
    return render(request, "billing/accept.html", {"quote": quote, "deal": deal, "form": form,
                                                   "formset": formset, "subtotal": subtotal})


@login_required
@require_POST
def invoice_create(request, deal_pk):
    deal = get_object_or_404(Deal, pk=deal_pk)
    schedule = None
    if request.POST.get("schedule"):
        schedule = get_object_or_404(BillingSchedule, pk=request.POST["schedule"], deal=deal)
        if schedule.invoice_id:
            messages.error(request, "この予定の請求書は作成済みです。")
            return redirect(schedule.invoice)
    inv = create_invoice(deal, request.user, schedule, use_quote_lines=request.POST.get("mode") == "lines")
    messages.success(request, f"請求書 {inv.number} を作成しました。内容を確認して発行してください。")
    return redirect("invoice_edit", inv.pk)


@login_required
def invoice_edit(request, pk):
    inv = get_object_or_404(Invoice.objects.select_related("deal", "deal__customer"), pk=pk)
    if not inv.is_editable:
        messages.error(request, "発行済みの請求書は編集できません。")
        return redirect(inv)
    form = InvoiceForm(request.POST or None, instance=inv)
    formset = InvoiceLineFormSet(request.POST or None, instance=inv, prefix="lines")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            _save_positions(formset)
        messages.success(request, "請求書を保存しました。")
        return redirect("invoice_edit" if "stay" in request.POST else "invoice_detail", inv.pk)
    return render(request, "billing/invoice_edit.html", {"invoice": inv, "form": form, "formset": formset})


@login_required
def invoice_detail(request, pk):
    inv = get_object_or_404(Invoice.objects.select_related("deal", "deal__customer", "created_by")
                            .prefetch_related("lines", "payments__created_by"), pk=pk)
    form = PaymentForm(initial={"amount": max(inv.balance, 0)})
    schedule = getattr(inv, "schedule", None)
    return render(request, "billing/invoice_detail.html", {
        "invoice": inv, "totals": inv.totals, "payment_form": form, "schedule": schedule})


@login_required
@require_POST
def invoice_issue(request, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    if not inv.is_editable:
        messages.error(request, "この請求書は発行済みです。")
        return redirect(inv)
    if not inv.lines.exists() or inv.totals.total <= 0:
        messages.error(request, "請求金額が 0 円です。明細を確認してください。")
        return redirect(inv)
    from documents.services import archive_invoice

    with transaction.atomic():
        inv.status = Invoice.Status.ISSUED
        inv.issued_at = timezone.now()
        inv.save(update_fields=["status", "issued_at", "updated_at"])
        archive_invoice(inv, request.user)
        log(inv.deal, request.user, f"請求書 {inv.number} を発行（¥{inv.totals.total:,}）")
    messages.success(request, f"請求書 {inv.number} を発行しました。PDF の控えを保存しました。")
    return redirect(inv)


@login_required
@require_POST
def invoice_revert(request, pk):
    """発行済みを下書きに戻す（管理者のみ・入金登録前のみ）。保存済みの PDF 控えは残る"""
    if not request.user.is_staff:
        raise PermissionDenied
    inv = get_object_or_404(Invoice, pk=pk)
    if inv.payments.exists():
        messages.error(request, "入金が登録されている請求書は下書きに戻せません。")
        return redirect(inv)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "下書きに戻す理由を入力してください。")
        return redirect(inv)
    inv.status = Invoice.Status.DRAFT
    inv.save(update_fields=["status", "updated_at"])
    log(inv.deal, request.user, f"請求書 {inv.number} を下書きに戻した（理由: {reason}）")
    messages.success(request, "下書きに戻しました。修正して再発行してください（前回の PDF は控えに残っています）。")
    return redirect("invoice_edit", inv.pk)


@login_required
@require_POST
def invoice_delete(request, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    if not inv.is_editable or inv.payments.exists():
        messages.error(request, "発行済みの請求書は削除できません。")
        return redirect(inv)
    from documents.models import IssuedDocument

    if IssuedDocument.objects.filter(number=inv.number).exists():
        messages.error(request, "一度発行した請求書は削除できません（番号を欠番にしないため）。")
        return redirect(inv)
    deal = inv.deal
    log(deal, request.user, f"下書きの請求書 {inv.number} を削除")
    inv.delete()
    messages.success(request, "下書きの請求書を削除しました。")
    return redirect(deal.get_absolute_url() + "#billing")


@login_required
@require_POST
def payment_add(request, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    if inv.is_editable:
        messages.error(request, "発行前の請求書には入金を登録できません。")
        return redirect(inv)
    form = PaymentForm(request.POST)
    if form.is_valid():
        p = form.save(commit=False)
        p.invoice = inv
        p.created_by = request.user
        p.save()
        log(inv.deal, request.user, f"請求書 {inv.number} に入金 ¥{p.amount:,}（{p.date:%Y/%m/%d}）")
        messages.success(request, "入金を登録しました。")
    else:
        messages.error(request, "入金を登録できません: " + " ".join(e for errs in form.errors.values() for e in errs))
    return redirect(inv)


@login_required
@require_POST
def payment_delete(request, pk):
    p = get_object_or_404(Payment.objects.select_related("invoice__deal"), pk=pk)
    if not (request.user.is_staff or request.user == p.created_by):
        raise PermissionDenied
    inv = p.invoice
    log(inv.deal, request.user, f"請求書 {inv.number} の入金 ¥{p.amount:,}（{p.date:%Y/%m/%d}）を取消")
    p.delete()
    messages.success(request, "入金を取り消しました。")
    return redirect(inv)


TABS = [
    ("todo", "請求待ち"), ("draft", "下書き"), ("unpaid", "未入金"), ("overdue", "期限超過"),
    ("paid", "入金済"), ("all", "すべての請求書"),
]


@login_required
def invoice_list(request):
    tab = request.GET.get("tab", "todo")
    today = timezone.localdate()
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    todo = (BillingSchedule.objects.filter(invoice__isnull=True, billing_month__lte=next_month)
            .select_related("deal", "deal__customer").order_by("billing_month", "deal__number"))
    invoices = Invoice.objects.select_related("deal", "deal__customer").prefetch_related("lines", "payments")
    q = request.GET.get("q", "").strip()
    if q:
        invoices = invoices.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(deal__customer__name__icontains=q))
        todo = todo.filter(Q(deal__number__icontains=q) | Q(deal__title__icontains=q)
                           | Q(deal__customer__name__icontains=q))
    issued = [i for i in invoices if i.status == Invoice.Status.ISSUED]
    groups = {
        "draft": [i for i in invoices if i.status == Invoice.Status.DRAFT],
        "unpaid": [i for i in issued if i.payment_status[0] in ("unpaid", "partial", "overdue")],
        "overdue": [i for i in issued if i.balance > 0 and i.due_date and i.due_date < today],
        "paid": [i for i in issued if i.payment_status[0] == "paid"],
        "all": list(invoices),
    }
    counts = {"todo": len(todo), **{k: len(v) for k, v in groups.items()}}
    rows = groups.get(tab, [])
    outstanding = sum(i.balance for i in groups["unpaid"])
    return render(request, "billing/invoice_list.html", {
        "tab": tab, "tabs": [(k, label, counts[k]) for k, label in TABS], "todo": todo,
        "page_obj": Paginator(rows, 50).get_page(request.GET.get("page")), "outstanding": outstanding,
        "querystring": f"tab={tab}" + (f"&q={q}" if q else ""),
    })
