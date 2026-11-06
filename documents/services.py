"""見積書・請求書の PDF 生成と原本保存"""
from django.db.models import Max

from catalog.models import CompanySettings

from .models import IssuedDocument
from .pdf import render_pdf


def quote_context(quote, draft=False):
    return {"doc": quote, "deal": quote.deal, "customer": quote.deal.customer, "company": CompanySettings.load(),
            "lines": list(quote.lines.all()), "totals": quote.totals, "draft": draft}


def invoice_context(invoice, draft=False):
    return {"doc": invoice, "deal": invoice.deal, "customer": invoice.deal.customer,
            "company": CompanySettings.load(), "lines": list(invoice.lines.all()), "totals": invoice.totals,
            "draft": draft}


def quote_pdf(quote, draft=False):
    return render_pdf("documents/quote_pdf.html", quote_context(quote, draft))


def invoice_pdf(invoice, draft=False):
    return render_pdf("documents/invoice_pdf.html", invoice_context(invoice, draft))


def _archive(doc_type, obj, pdf, user):
    totals = obj.totals
    last = IssuedDocument.objects.filter(number=obj.number).aggregate(m=Max("revision"))["m"] or 0
    return IssuedDocument.objects.create(
        doc_type=doc_type, number=obj.number, revision=last + 1, title=obj.title,
        customer_name=obj.deal.customer.name, deal_number=obj.deal.number, issue_date=obj.issue_date,
        subtotal=totals.subtotal, tax=totals.tax, total=totals.total, pdf=pdf, issued_by=user,
    )


def archive_quote(quote, user):
    return _archive(IssuedDocument.DocType.QUOTE, quote, quote_pdf(quote), user)


def archive_invoice(invoice, user):
    return _archive(IssuedDocument.DocType.INVOICE, invoice, invoice_pdf(invoice), user)


def latest_archive(number):
    return IssuedDocument.objects.filter(number=number).order_by("-revision").first()
