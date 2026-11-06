from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from deals.models import Deal, DealActivity

from .forms import LineCostForm, LineMaterialFormSet, QuoteForm, QuoteLineFormSet
from .models import Quote, QuoteLine


def log(deal, user, body):
    DealActivity.objects.create(deal=deal, user=user, kind=DealActivity.Kind.CHANGED, body=body)


def _save_positions(formset):
    """画面の並び順で position を振り直し、削除指定の行を消す"""
    position = 0
    for form in formset.ordered_forms if formset.can_order else formset.forms:
        if not form.has_changed() and not form.instance.pk:
            continue
        if formset.can_delete and formset._should_delete_form(form):
            if form.instance.pk:
                form.instance.delete()
            continue
        obj = form.save(commit=False)
        position += 1
        obj.position = position
        obj.save()


@login_required
def quote_list(request):
    qs = Quote.objects.select_related("deal", "deal__customer", "created_by").prefetch_related("lines")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(deal__customer__name__icontains=q))
    if status:
        qs = qs.filter(status=status)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "quotes/quote_list.html", {
        "page_obj": page, "statuses": Quote.Status.choices, "querystring": params.urlencode()})


@login_required
@require_POST
def quote_create(request, deal_pk):
    deal = get_object_or_404(Deal, pk=deal_pk)
    quote = Quote.create_for(deal, request.user)
    log(deal, request.user, f"見積 {quote.number} を作成")
    return redirect("quote_edit", quote.pk)


@login_required
def quote_edit(request, pk):
    quote = get_object_or_404(Quote.objects.select_related("deal", "deal__customer"), pk=pk)
    if not quote.is_editable:
        messages.error(request, "提出済みの見積は編集できません。修正する場合は「新しい版を作成」してください。")
        return redirect(quote)
    form = QuoteForm(request.POST or None, instance=quote)
    formset = QuoteLineFormSet(request.POST or None, instance=quote, prefix="lines")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            _save_positions(formset)
        messages.success(request, "見積を保存しました。")
        if request.POST.get("cost_line", "").isdigit():
            line = quote.lines.filter(pk=int(request.POST["cost_line"])).first()
            if line:
                return redirect("quote_line_cost", quote.pk, line.pk)
        return redirect("quote_edit" if "stay" in request.POST else "quote_detail", quote.pk)
    return render(request, "quotes/quote_edit.html", {"quote": quote, "form": form, "formset": formset})


@login_required
def quote_detail(request, pk):
    quote = get_object_or_404(
        Quote.objects.select_related("deal", "deal__customer", "created_by")
        .prefetch_related("lines__materials"), pk=pk)
    return render(request, "quotes/quote_detail.html", {
        "quote": quote, "lines": quote.lines.all(), "totals": quote.totals, "cost": quote.cost_summary,
        "other_versions": quote.deal.quotes.exclude(pk=quote.pk).order_by("-version"),
    })


@login_required
def quote_line_cost(request, pk, line_pk):
    quote = get_object_or_404(Quote.objects.select_related("deal"), pk=pk)
    line = get_object_or_404(QuoteLine, pk=line_pk, quote=quote)
    editable = quote.is_editable
    form = LineCostForm(request.POST or None, instance=line)
    formset = LineMaterialFormSet(request.POST or None, instance=line, prefix="mat")
    if request.method == "POST":
        if not editable:
            messages.error(request, "提出済みの見積は変更できません。")
            return redirect(request.path)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                _save_positions(formset)
                line.refresh_from_db()
                if "apply_price" in request.POST and line.suggested_unit_price is not None:
                    line.unit_price = line.suggested_unit_price
                    line.save(update_fields=["unit_price"])
                    messages.success(request, f"単価を {line.unit_price:,} 円に設定しました。")
                else:
                    messages.success(request, "原価を保存しました。")
            return redirect("quote_edit" if "back" in request.POST else "quote_line_cost", quote.pk,
                            *([] if "back" in request.POST else [line.pk]))
    return render(request, "quotes/line_cost.html", {
        "quote": quote, "line": line, "form": form, "formset": formset, "editable": editable})


@login_required
@require_POST
def quote_copy(request, pk):
    src = get_object_or_404(Quote, pk=pk)
    new = src.copy_as_new_version(request.user)
    log(src.deal, request.user, f"見積 {src.number} を複製して {new.number} を作成")
    messages.success(request, f"新しい版 {new.number} を作成しました。")
    return redirect("quote_edit", new.pk)


@login_required
@require_POST
def quote_issue(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if not quote.is_editable:
        messages.error(request, "この見積は既に発行済みです。")
        return redirect(quote)
    if not quote.lines.exists():
        messages.error(request, "明細が 1 行もありません。")
        return redirect(quote)
    from documents.services import archive_quote

    with transaction.atomic():
        quote.status = Quote.Status.SUBMITTED
        quote.issued_at = timezone.now()
        quote.save(update_fields=["status", "issued_at", "updated_at"])
        archive_quote(quote, request.user)
        deal = quote.deal
        if deal.phase in (Deal.Phase.LEAD, Deal.Phase.PROPOSAL):
            deal.phase = Deal.Phase.ESTIMATE
        if not deal.amount:
            deal.amount = quote.totals.subtotal  # 見込み金額が未入力なら見積額を入れる
        deal.save()
        log(quote.deal, request.user, f"見積 {quote.number} を発行（合計 ¥{quote.totals.total:,}）")
    messages.success(request, f"見積 {quote.number} を発行しました。PDF の控えを保存しました。")
    return redirect(quote)


@login_required
@require_POST
def quote_mark_lost(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if quote.status == Quote.Status.ACCEPTED:
        messages.error(request, "受注済みの見積は失注にできません。")
        return redirect(quote)
    quote.status = Quote.Status.LOST
    quote.save(update_fields=["status", "updated_at"])
    log(quote.deal, request.user, f"見積 {quote.number} を失注に変更")
    messages.success(request, "見積を失注にしました。")
    return redirect(quote)


@login_required
@require_POST
def quote_delete(request, pk):
    quote = get_object_or_404(Quote, pk=pk)
    if not quote.is_editable:
        messages.error(request, "発行済みの見積は削除できません。")
        return redirect(quote)
    deal = quote.deal
    log(deal, request.user, f"下書きの見積 {quote.number} を削除")
    quote.delete()
    messages.success(request, "下書きの見積を削除しました。")
    return redirect(deal)
