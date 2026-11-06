import csv
from urllib.parse import urlencode
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.utils import display_name

from .forms import CommentForm, CustomerForm, DealForm, DealSearchForm, describe_changes
from .models import Customer, Deal, DealActivity


# ---------- ダッシュボード ----------

# 上限の先頭桁 → 目盛り分割数（目盛り間隔が 1, 2, 5 系の切りの良い値になる組み合わせ）
_NICE_STEPS = ((1, 5), (2, 4), (2.5, 5), (5, 5), (10, 5))


def nice_scale(value):
    """グラフ軸の (上限, 分割数) を返す。上限は 1, 2, 2.5, 5 ×10^n に切り上げる"""
    if value <= 0:
        return 0, 0
    mag = 10 ** (len(str(int(value))) - 1)
    for step, divisions in _NICE_STEPS:
        if value <= step * mag:
            return int(step * mag), divisions
    return int(10 * mag), 5


def nice_ceiling(value):
    return nice_scale(value)[0]

@login_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    open_deals = Deal.objects.filter(phase__in=Deal.OPEN_PHASES)

    phase_rows = []
    agg = {r["phase"]: r for r in Deal.objects.values("phase").annotate(n=Count("id"), total=Sum("amount"))}
    max_total = max([r["total"] or 0 for r in agg.values()] + [1])
    for value, label in Deal.Phase.choices:
        r = agg.get(value, {})
        total = r.get("total") or 0
        phase_rows.append({
            "value": value, "label": label, "count": r.get("n", 0),
            "total": total, "pct": round(total * 100 / max_total),
        })

    totals = open_deals.aggregate(pipeline=Sum("amount"), weighted=Sum(F("amount") * F("probability")))
    pipeline_total = totals["pipeline"] or 0
    weighted_total = (totals["weighted"] or 0) // 100

    won_this_month = Deal.objects.filter(phase__in=Deal.WON_PHASES, closed_date__gte=month_start, closed_date__lt=next_month)
    closed_this_month = Deal.objects.filter(phase__in=Deal.CLOSED_PHASES, closed_date__gte=month_start,
                                            closed_date__lt=next_month)
    won_count = won_this_month.count()
    closed_count = closed_this_month.count()

    # 直近12か月の受注額（クローズ日ベース）
    first_month = month_start
    for _ in range(11):
        first_month = (first_month - timedelta(days=1)).replace(day=1)
    monthly = {
        r["m"]: r for r in Deal.objects.filter(phase__in=Deal.WON_PHASES, closed_date__gte=first_month)
        .annotate(m=TruncMonth("closed_date")).values("m").annotate(total=Sum("amount"), n=Count("id"))
    }
    months, m = [], first_month
    while m <= month_start:
        r = monthly.get(m, {})
        months.append({"month": m, "total": r.get("total") or 0, "count": r.get("n", 0)})
        m = (m + timedelta(days=32)).replace(day=1)
    month_max = max([x["total"] for x in months] + [0])
    scale_max, divisions = nice_scale(month_max)
    for x in months:
        x["pct"] = round(x["total"] * 100 / scale_max, 1) if scale_max else 0

    context = {
        "months": months,
        "month_ticks": [scale_max * i // divisions for i in range(divisions, 0, -1)],
        "year_total": sum(x["total"] for x in months),
        "today": today,
        "open_count": open_deals.count(),
        "pipeline_total": pipeline_total,
        "weighted_total": weighted_total,
        "won_month_total": won_this_month.aggregate(s=Sum("amount"))["s"] or 0,
        "won_month_count": won_count,
        "win_rate": round(won_count * 100 / closed_count) if closed_count else None,
        "phase_rows": phase_rows,
        "overdue_deals": open_deals.filter(expected_close_date__lt=today)
            .select_related("customer", "owner").order_by("expected_close_date")[:10],
        "upcoming_deals": open_deals.filter(expected_close_date__gte=today,
                                            expected_close_date__lte=today + timedelta(days=30))
            .select_related("customer", "owner").order_by("expected_close_date")[:10],
        "my_deals": open_deals.filter(owner=request.user)
            .select_related("customer").order_by("expected_close_date")[:10],
    }
    return render(request, "deals/dashboard.html", context)


# ---------- 案件 ----------

def filter_deals(params):
    form = DealSearchForm(params or None)
    qs = Deal.objects.select_related("customer", "owner")
    sort = "-updated_at"
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            qs = qs.filter(Q(number__icontains=d["q"]) | Q(title__icontains=d["q"])
                           | Q(customer__name__icontains=d["q"]) | Q(description__icontains=d["q"]))
        if d["phase"] == "open":
            qs = qs.filter(phase__in=Deal.OPEN_PHASES)
        elif d["phase"] == "won_all":
            qs = qs.filter(phase__in=Deal.WON_PHASES)
        elif d["phase"]:
            qs = qs.filter(phase=d["phase"])
        if d["owner"]:
            qs = qs.filter(owner=d["owner"])
        if d["customer"]:
            qs = qs.filter(customer=d["customer"])
        if d["close_from"]:
            qs = qs.filter(expected_close_date__gte=d["close_from"])
        if d["close_to"]:
            qs = qs.filter(expected_close_date__lte=d["close_to"])
        sort = d["sort"] or sort
    if sort == "expected_close_date":
        qs = qs.order_by(F("expected_close_date").asc(nulls_last=True), "-updated_at")
    else:
        qs = qs.order_by(sort, "-id")
    return form, qs


@login_required
def deal_list(request):
    form, qs = filter_deals(request.GET)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "deals/deal_list.html", {
        "form": form, "page_obj": page, "total_count": qs.count(),
        "total_amount": qs.aggregate(s=Sum("amount"))["s"] or 0,
        "querystring": params.urlencode(),
    })


@login_required
def deal_export_csv(request):
    _, qs = filter_deals(request.GET)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="deals.csv"'
    response.write("﻿")  # Excel用BOM
    w = csv.writer(response)
    w.writerow(["案件番号", "案件名", "顧客", "担当者", "フェーズ", "見込み金額", "確度(%)", "加重金額",
                "受注予定日", "クローズ日", "更新日時"])
    for d in qs:
        w.writerow([
            d.number, d.title, d.customer.name,
            display_name(d.owner) if d.owner else "",
            d.get_phase_display(), d.amount, d.probability, d.weighted_amount,
            d.expected_close_date or "", d.closed_date or "",
            timezone.localtime(d.updated_at).strftime("%Y-%m-%d %H:%M"),
        ])
    return response


class DealDetailView(LoginRequiredMixin, DetailView):
    model = Deal
    queryset = Deal.objects.select_related("customer", "owner", "created_by")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["activities"] = self.object.activities.select_related("user")
        ctx["comment_form"] = kwargs.get("comment_form") or CommentForm()
        return ctx


@login_required
@require_POST
def deal_add_comment(request, pk):
    deal = get_object_or_404(Deal, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        DealActivity.objects.create(deal=deal, user=request.user, kind=DealActivity.Kind.COMMENT,
                                    body=form.cleaned_data["body"])
        deal.save(update_fields=["updated_at"])
        messages.success(request, "コメントを追加しました。")
        return redirect(deal)
    view = DealDetailView(request=request, kwargs={"pk": pk}, object=deal)
    return render(request, "deals/deal_detail.html", view.get_context_data(comment_form=form))


@login_required
@require_POST
def activity_delete(request, pk):
    act = get_object_or_404(DealActivity, pk=pk, kind=DealActivity.Kind.COMMENT)
    if not (request.user.is_staff or request.user == act.user):
        messages.error(request, "このコメントは削除できません。")
    else:
        act.delete()
        messages.success(request, "コメントを削除しました。")
    return redirect(act.deal)


class DealCreateView(LoginRequiredMixin, CreateView):
    model = Deal
    form_class = DealForm

    def dispatch(self, request, *args, **kwargs):
        self.parent = None
        if request.GET.get("parent"):
            self.parent = get_object_or_404(Deal, pk=request.GET["parent"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = {"owner": self.request.user}
        if self.parent:
            p = self.parent
            initial.update(customer=p.customer, title=f"{p.title} 追加工事", site_address=p.site_address,
                           phase=Deal.Phase.ESTIMATE, owner=p.owner or self.request.user)
        elif "customer" in self.request.GET:
            initial["customer"] = self.request.GET["customer"]
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["parent"] = self.parent
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.parent = self.parent
        response = super().form_valid(form)
        DealActivity.objects.create(deal=self.object, user=self.request.user,
                                    kind=DealActivity.Kind.CREATED, body="案件を作成")
        messages.success(self.request, "案件を登録しました。")
        return response


class DealUpdateView(LoginRequiredMixin, UpdateView):
    model = Deal
    form_class = DealForm

    def form_valid(self, form):
        original = Deal.objects.get(pk=self.object.pk)
        old = {name: getattr(original, name) for name in form.fields}
        response = super().form_valid(form)
        body = describe_changes(form, old)
        if body:
            DealActivity.objects.create(deal=self.object, user=self.request.user,
                                        kind=DealActivity.Kind.CHANGED, body=body)
        messages.success(self.request, "案件を更新しました。")
        return response


class DealDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """削除は担当者・作成者・管理者のみ"""
    model = Deal
    success_url = reverse_lazy("deal_list")

    def test_func(self):
        deal = self.get_object()
        u = self.request.user
        return u.is_staff or u == deal.owner or u == deal.created_by

    def form_valid(self, form):
        messages.success(self.request, f"案件「{self.object}」を削除しました。")
        return super().form_valid(form)


# ---------- 顧客 ----------

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    paginate_by = 25

    def get_queryset(self):
        qs = Customer.objects.annotate(
            deal_count=Count("deals"),
            open_count=Count("deals", filter=Q(deals__phase__in=Deal.OPEN_PHASES)),
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(contact_person__icontains=q) | Q(email__icontains=q))
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["querystring"] = urlencode({"q": ctx["q"]}) if ctx["q"] else ""
        return ctx


class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["deals"] = self.object.deals.select_related("owner").order_by("-updated_at")
        return ctx


class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm

    def form_valid(self, form):
        messages.success(self.request, "顧客を登録しました。")
        return super().form_valid(form)


class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm

    def form_valid(self, form):
        messages.success(self.request, "顧客情報を更新しました。")
        return super().form_valid(form)


@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if not request.user.is_staff:
        messages.error(request, "顧客の削除は管理者のみ可能です。")
        return redirect(customer)
    if request.method == "POST":
        try:
            customer.delete()
        except ProtectedError:
            messages.error(request, "この顧客には案件が登録されているため削除できません。")
            return redirect(customer)
        messages.success(request, f"顧客「{customer}」を削除しました。")
        return redirect("customer_list")
    return render(request, "deals/customer_confirm_delete.html", {"object": customer})
