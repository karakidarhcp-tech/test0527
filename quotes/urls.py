from django.urls import path

from . import views

urlpatterns = [
    path("", views.quote_list, name="quote_list"),
    path("new/<int:deal_pk>/", views.quote_create, name="quote_create"),
    path("<int:pk>/", views.quote_detail, name="quote_detail"),
    path("<int:pk>/edit/", views.quote_edit, name="quote_edit"),
    path("<int:pk>/lines/<int:line_pk>/cost/", views.quote_line_cost, name="quote_line_cost"),
    path("<int:pk>/copy/", views.quote_copy, name="quote_copy"),
    path("<int:pk>/issue/", views.quote_issue, name="quote_issue"),
    path("<int:pk>/lost/", views.quote_mark_lost, name="quote_mark_lost"),
    path("<int:pk>/delete/", views.quote_delete, name="quote_delete"),
]
