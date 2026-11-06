from django.contrib import admin

from .models import IssuedDocument


@admin.register(IssuedDocument)
class IssuedDocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "revision", "doc_type", "customer_name", "issue_date", "total", "issued_at")
    list_filter = ("doc_type",)
    search_fields = ("number", "customer_name", "title")
    exclude = ("pdf",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
