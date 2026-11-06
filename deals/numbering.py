"""採番ロジック（番号ルールは CLAUDE.md を参照）

- 案件番号: YYMM + 月内連番3桁（例 2611001）
- 追加工事: 親案件番号-A{n}
- 書類番号: 案件番号-Q{n}（見積の版）/ -B{n}（請求書）
"""
from django.db import transaction
from django.utils import timezone


def next_value(key):
    """key ごとの連番を 1 つ進めて返す。行ロックで同時採番の重複を防ぐ"""
    from .models import NumberSequence

    with transaction.atomic():
        seq, _ = NumberSequence.objects.select_for_update().get_or_create(key=key)
        seq.last += 1
        seq.save(update_fields=["last"])
        return seq.last


def next_deal_number(date=None):
    date = date or timezone.localdate()
    prefix = date.strftime("%y%m")
    n = next_value(prefix)
    if n > 999:
        raise ValueError(f"{prefix} の案件番号が 999 件を超えました")
    return f"{prefix}{n:03d}"


def next_child_number(parent):
    return f"{parent.number}-A{next_value(parent.number + '-A')}"


def next_document_number(deal, kind):
    """kind: "Q"（見積）または "B"（請求書）。返り値は (番号文字列, 連番)"""
    n = next_value(f"{deal.number}-{kind}")
    return f"{deal.number}-{kind}{n}", n
