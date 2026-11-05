from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("deals/", views.deal_list, name="deal_list"),
    path("deals/export.csv", views.deal_export_csv, name="deal_export_csv"),
    path("deals/new/", views.DealCreateView.as_view(), name="deal_create"),
    path("deals/<int:pk>/", views.DealDetailView.as_view(), name="deal_detail"),
    path("deals/<int:pk>/edit/", views.DealUpdateView.as_view(), name="deal_update"),
    path("deals/<int:pk>/delete/", views.DealDeleteView.as_view(), name="deal_delete"),
    path("deals/<int:pk>/comments/", views.deal_add_comment, name="deal_add_comment"),
    path("activities/<int:pk>/delete/", views.activity_delete, name="activity_delete"),
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/new/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="customer_delete"),
]
