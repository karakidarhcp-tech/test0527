from django.urls import path

from . import views

urlpatterns = [
    path("", views.invoice_list, name="invoice_list"),
    path("accept/<int:pk>/", views.quote_accept, name="quote_accept"),
    path("new/<int:deal_pk>/", views.invoice_create, name="invoice_create"),
    path("<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("<int:pk>/edit/", views.invoice_edit, name="invoice_edit"),
    path("<int:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("<int:pk>/revert/", views.invoice_revert, name="invoice_revert"),
    path("<int:pk>/delete/", views.invoice_delete, name="invoice_delete"),
    path("<int:pk>/payments/", views.payment_add, name="payment_add"),
    path("payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
]
