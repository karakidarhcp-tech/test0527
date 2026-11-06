from django.urls import path

from . import views

urlpatterns = [
    path("items/", views.ItemListView.as_view(), name="item_list"),
    path("items/new/", views.ItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/edit/", views.ItemUpdateView.as_view(), name="item_update"),
    path("items/import/", views.item_import, name="item_import"),
    path("items/template.xlsx", views.item_template, name="item_template"),
    path("items/search.json", views.item_search_json, name="item_search_json"),
    path("settings/", views.company_settings, name="company_settings"),
]
