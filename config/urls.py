from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("master/", include("catalog.urls")),
    path("quotes/", include("quotes.urls")),
    path("billing/", include("billing.urls")),
    path("documents/", include("documents.urls")),
    path("", include("deals.urls")),
]
