from django.contrib import admin

from .models import Customer, Deal, DealActivity


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


@admin.register(DealActivity)
class DealActivityAdmin(admin.ModelAdmin):
    list_display = ("deal", "kind", "user", "created_at")
    list_filter = ("kind",)
