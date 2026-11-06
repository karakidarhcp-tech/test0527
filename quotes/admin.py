from django.contrib import admin

from .models import LineMaterial, Quote, QuoteLine


class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "deal", "status", "issue_date")
    list_filter = ("status",)
    search_fields = ("number", "title")
    inlines = [QuoteLineInline]


admin.site.register(LineMaterial)
