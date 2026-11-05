from django.contrib import admin

from .models import Customer, Deal


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "email", "phone", "updated_at")
    search_fields = ("name", "contact_person", "email")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "customer", "owner", "phase", "amount", "probability", "expected_close_date")
    list_filter = ("phase", "owner")
    search_fields = ("title", "customer__name", "description")
    autocomplete_fields = ("customer",)
