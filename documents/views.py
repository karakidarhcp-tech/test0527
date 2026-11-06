from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.http import content_disposition_header

from billing.models import Invoice
from quotes.models import Quote

from .models import IssuedDocument
from .services import invoice_pdf, latest_archive, quote_pdf


def pdf_response(data, filename, inline=True):
    resp = HttpResponse(bytes(data), content_type="application/pdf")
    resp["Content-Disposition"] = content_disposition_header(not inline, filename)
    return resp


@login_required
def quote_pdf_view(request, pk):
    """発行済みなら保存した原本、下書きなら「下書き」透かし入りのプレビュー"""
    quote = get_object_or_404(Quote.objects.select_related("deal__customer"), pk=pk)
    if not quote.is_editable:
        doc = latest_archive(quote.number)
        if doc:
            return pdf_response(doc.pdf, doc.filename)
    return pdf_response(quote_pdf(quote, draft=quote.is_editable), f"見積書_{quote.number}.pdf")


@login_required
def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("deal__customer"), pk=pk)
    if not invoice.is_editable:
        doc = latest_archive(invoice.number)
        if doc:
            return pdf_response(doc.pdf, doc.filename)
    return pdf_response(invoice_pdf(invoice, draft=invoice.is_editable), f"請求書_{invoice.number}.pdf")


@login_required
def document_list(request):
    """発行済み書類の検索（日付・金額・取引先）"""
    qs = IssuedDocument.objects.defer("pdf").select_related("issued_by")
    g = request.GET
    if g.get("q"):
        q = g["q"].strip()
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(customer_name__icontains=q))
    if g.get("customer"):
        qs = qs.filter(customer_name__icontains=g["customer"].strip())
    if g.get("doc_type"):
        qs = qs.filter(doc_type=g["doc_type"])
    for key, lookup in (("date_from", "issue_date__gte"), ("date_to", "issue_date__lte")):
        if g.get(key):
            qs = qs.filter(**{lookup: g[key]})
    for key, lookup in (("amount_min", "total__gte"), ("amount_max", "total__lte")):
        v = g.get(key, "").replace(",", "").strip()
        if v.isdigit():
            qs = qs.filter(**{lookup: int(v)})
    page = Paginator(qs, 50).get_page(g.get("page"))
    params = g.copy()
    params.pop("page", None)
    return render(request, "documents/document_list.html", {
        "page_obj": page, "doc_types": IssuedDocument.DocType.choices, "querystring": params.urlencode()})


@login_required
def document_download(request, pk):
    doc = get_object_or_404(IssuedDocument, pk=pk)
    return pdf_response(doc.pdf, doc.filename, inline=request.GET.get("download") != "1")
