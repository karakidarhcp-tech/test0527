from django.urls import path

from . import views

urlpatterns = [
    path("", views.document_list, name="document_list"),
    path("<int:pk>/", views.document_download, name="document_download"),
    path("quote/<int:pk>.pdf", views.quote_pdf_view, name="quote_pdf"),
    path("invoice/<int:pk>.pdf", views.invoice_pdf_view, name="invoice_pdf"),
]
