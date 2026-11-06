from django.contrib import admin

from .models import CompanySettings, Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("code", "category", "name", "spec", "unit", "cost", "price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name", "spec")


admin.site.register(CompanySettings)
