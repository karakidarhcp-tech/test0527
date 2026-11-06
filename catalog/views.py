from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import CompanySettingsForm, ItemForm, ItemImportForm
from .importer import build_template, import_items
from .models import CompanySettings, Item
from .pricing import price_from_cost


class ItemListView(LoginRequiredMixin, ListView):
    model = Item
    paginate_by = 50
    template_name = "catalog/item_list.html"

    def get_queryset(self):
        qs = Item.objects.all()
        g = self.request.GET
        if g.get("q"):
            q = g["q"].strip()
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(spec__icontains=q))
        if g.get("category"):
            qs = qs.filter(category=g["category"])
        if g.get("inactive") != "1":
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(querystring=params.urlencode(), categories=Item.Category.choices, settings=CompanySettings.load())
        s = ctx["settings"]
        for item in ctx["object_list"]:
            item.calc_price = item.price if item.price is not None else price_from_cost(
                item.cost, s.target_margin, s.price_rounding)
        return ctx


class ItemCreateView(LoginRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("item_list")

    def form_valid(self, form):
        messages.success(self.request, "品目を登録しました。")
        return super().form_valid(form)


class ItemUpdateView(LoginRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("item_list")

    def form_valid(self, form):
        messages.success(self.request, "品目を更新しました。")
        return super().form_valid(form)


@login_required
def item_import(request):
    form = ItemImportForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        result = import_items(form.cleaned_data["file"])
        if not result.errors:
            messages.success(request, f"取り込みました: 新規 {result.created} 件 / 更新 {result.updated} 件")
            return redirect("item_list")
    return render(request, "catalog/item_import.html", {"form": form, "result": result})


@login_required
def item_template(request):
    resp = HttpResponse(build_template(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = "attachment; filename*=UTF-8''%E5%8E%9F%E4%BE%A1%E8%A1%A8%E3%83%86%E3%83%B3%E3%83%97%E3%83%AC%E3%83%BC%E3%83%88.xlsx"
    return resp


@login_required
def item_search_json(request):
    """見積の材料入力で使う品目検索（最大 20 件）"""
    from django.http import JsonResponse

    q = request.GET.get("q", "").strip()
    qs = Item.objects.filter(is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(spec__icontains=q))
    return JsonResponse({"items": [
        {"id": i.pk, "label": str(i), "unit": i.unit, "cost": str(i.cost)} for i in qs[:20]
    ]})


@login_required
def company_settings(request):
    if not request.user.is_staff:
        raise PermissionDenied
    obj = CompanySettings.load()
    form = CompanySettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "会社設定を保存しました。")
        return redirect("company_settings")
    return render(request, "catalog/company_settings.html", {"form": form})
