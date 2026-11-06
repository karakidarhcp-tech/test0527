from django.contrib import admin

from .models import BillingSchedule, Invoice, InvoiceLine, Payment


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "deal", "status", "issue_date", "due_date")
    list_filter = ("status",)
    search_fields = ("number", "title")
    inlines = [InvoiceLineInline]


admin.site.register(BillingSchedule)
admin.site.register(Payment)
