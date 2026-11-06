"""既存の案件に案件番号を振る（作成日の年月 + 月内連番、作成順）"""
from collections import defaultdict
from zoneinfo import ZoneInfo

from django.db import migrations

JST = ZoneInfo("Asia/Tokyo")


def backfill(apps, schema_editor):
    Deal = apps.get_model("deals", "Deal")
    NumberSequence = apps.get_model("deals", "NumberSequence")
    counters = defaultdict(int)
    for seq in NumberSequence.objects.all():
        counters[seq.key] = seq.last
    for deal in Deal.objects.filter(number__isnull=True).order_by("created_at", "id"):
        prefix = deal.created_at.astimezone(JST).strftime("%y%m")
        counters[prefix] += 1
        deal.number = f"{prefix}{counters[prefix]:03d}"
        deal.save(update_fields=["number"])
    for key, last in counters.items():
        NumberSequence.objects.update_or_create(key=key, defaults={"last": last})


class Migration(migrations.Migration):
    dependencies = [("deals", "0003_project_numbering")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
