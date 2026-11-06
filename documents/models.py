import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class IssuedDocument(models.Model):
    """発行した書類の原本（PDF）。保存後は変更・削除できない"""

    class DocType(models.TextChoices):
        QUOTE = "quote", "見積書"
        INVOICE = "invoice", "請求書"

    doc_type = models.CharField("種別", max_length=20, choices=DocType.choices)
    number = models.CharField("書類番号", max_length=40, db_index=True)
    revision = models.PositiveIntegerField("発行回", default=1, help_text="同じ番号を再発行した場合に増える")
    title = models.CharField("件名", max_length=200)
    customer_name = models.CharField("取引先", max_length=200, db_index=True)
    deal_number = models.CharField("案件番号", max_length=30, db_index=True)
    issue_date = models.DateField("発行日（書類の日付）", db_index=True)
    subtotal = models.BigIntegerField("税抜金額")
    tax = models.BigIntegerField("消費税")
    total = models.BigIntegerField("税込金額", db_index=True)
    pdf = models.BinaryField("PDF")
    sha256 = models.CharField("SHA-256", max_length=64)
    size = models.PositiveIntegerField("サイズ(byte)")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="発行者", null=True,
                                  on_delete=models.SET_NULL)
    issued_at = models.DateTimeField("発行日時", auto_now_add=True)

    class Meta:
        verbose_name = "発行済み書類"
        verbose_name_plural = "発行済み書類"
        ordering = ["-issued_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["number", "revision"], name="unique_doc_revision")]

    def __str__(self):
        return f"{self.number}（{self.revision}回目）"

    def get_absolute_url(self):
        return reverse("document_download", args=[self.pk])

    @property
    def filename(self):
        suffix = f"_{self.revision}" if self.revision > 1 else ""
        return f"{self.get_doc_type_display()}_{self.number}{suffix}.pdf"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("発行済みの書類は変更できません。")
        data = bytes(self.pdf)
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.size = len(data)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("発行済みの書類は削除できません。")
