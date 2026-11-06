"""Excel / CSV の原価表を品目マスタに取り込む

- 先頭 10 行の中から「品名」を含む行を見出し行とみなす
- 列名の揺れを吸収する（下の COLUMN_ALIASES）
- 1 行でもエラーがあれば何も取り込まない（全件成功 or 全件中止）
- 品番があれば品番で、なければ「品名＋規格」で既存品目を探して更新、なければ新規作成
"""
import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Item

COLUMN_ALIASES = {
    "code": ["品番", "コード", "品目コード", "商品コード"],
    "category": ["分類", "区分", "カテゴリ", "種別"],
    "name": ["品名", "名称", "品目", "品目名", "材料名", "商品名"],
    "spec": ["規格", "仕様", "サイズ", "規格・仕様", "寸法"],
    "unit": ["単位"],
    "cost": ["原価", "原価単価", "仕入単価", "仕入値", "単価"],
    "price": ["売価", "標準売価", "定価", "販売単価"],
    "notes": ["備考", "メモ"],
}
CATEGORY_BY_LABEL = {label: value for value, label in Item.Category.choices}
CATEGORY_BY_LABEL.update({"材": "material", "板": "board", "金物": "hardware", "塗装": "finish"})
TEMPLATE_HEADERS = ["品番", "分類", "品名", "規格", "単位", "原価", "売価", "備考"]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)  # (行番号, メッセージ)


def _norm(v):
    return str(v).strip().replace("　", " ") if v is not None else ""


def read_rows(uploaded):
    """(行番号, 値リスト) を返す。xlsx / csv（UTF-8 or Shift_JIS）に対応"""
    name = uploaded.name.lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [(i, list(r)) for i, r in enumerate(ws.iter_rows(values_only=True), start=1)]
    if name.endswith(".csv"):
        raw = uploaded.read()
        for enc in ("utf-8-sig", "cp932"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("CSV の文字コードを判別できません（UTF-8 か Shift_JIS で保存してください）")
        return [(i, r) for i, r in enumerate(csv.reader(io.StringIO(text)), start=1)]
    raise ValueError("Excel（.xlsx）または CSV ファイルを選んでください（古い .xls は .xlsx で保存し直してください）")


def find_header(rows):
    for idx, (_, values) in enumerate(rows[:10]):
        labels = [_norm(v) for v in values]
        mapping = {}
        for key, aliases in COLUMN_ALIASES.items():
            for col, label in enumerate(labels):
                if label in aliases and key not in mapping:
                    mapping[key] = col
        if "name" in mapping:
            return idx, mapping
    return None, None


def _to_decimal(value, row_no, label, errors, required=False):
    s = _norm(value).replace(",", "").replace("¥", "").replace("円", "")
    if s == "":
        if required:
            errors.append((row_no, f"{label}が空です"))
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        errors.append((row_no, f"{label}「{value}」が数値ではありません"))
        return None
    if d < 0:
        errors.append((row_no, f"{label}がマイナスです"))
        return None
    return d


def import_items(uploaded):
    result = ImportResult()
    try:
        rows = read_rows(uploaded)
    except Exception as e:  # ファイル破損など
        result.errors.append((0, str(e) if isinstance(e, ValueError) else f"ファイルを読み込めません: {e}"))
        return result
    header_idx, cols = find_header(rows)
    if header_idx is None:
        result.errors.append((0, "見出し行が見つかりません。先頭 10 行以内に「品名」の列を作ってください"))
        return result
    if "cost" not in cols:
        result.errors.append((rows[header_idx][0], "「原価」（または 原価単価・仕入単価・単価）の列が必要です"))
        return result

    def cell(values, key):
        col = cols.get(key)
        return values[col] if col is not None and col < len(values) else None

    parsed = []
    for row_no, values in rows[header_idx + 1:]:
        name = _norm(cell(values, "name"))
        if not name:
            if any(_norm(v) for v in values):
                result.errors.append((row_no, "品名が空です"))
            else:
                result.skipped += 1
            continue
        errs_before = len(result.errors)
        cost = _to_decimal(cell(values, "cost"), row_no, "原価", result.errors, required=True)
        price = _to_decimal(cell(values, "price"), row_no, "売価", result.errors)
        cat_label = _norm(cell(values, "category"))
        category = CATEGORY_BY_LABEL.get(cat_label, Item.Category.OTHER if cat_label else Item.Category.MATERIAL)
        if len(result.errors) > errs_before:
            continue
        parsed.append(dict(
            code=_norm(cell(values, "code")), category=category, name=name[:200],
            spec=_norm(cell(values, "spec"))[:200], unit=_norm(cell(values, "unit"))[:20] or "個",
            cost=cost.quantize(Decimal("0.01")), price=int(price) if price is not None else None,
            notes=_norm(cell(values, "notes"))[:300],
        ))
    if result.errors:
        return result

    with transaction.atomic():
        for data in parsed:
            if data["code"]:
                item = Item.objects.filter(code=data["code"]).first()
            else:
                item = Item.objects.filter(code="", name=data["name"], spec=data["spec"]).first()
            if item:
                for k, v in data.items():
                    setattr(item, k, v)
                item.is_active = True
                item.save()
                result.updated += 1
            else:
                Item.objects.create(**data)
                result.created += 1
    return result


def build_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "原価表"
    ws.append(TEMPLATE_HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDE6F7")
    ws.append(["W-001", "板材・合板", "シナランバーコア", "21mm 4×8", "枚", 9800, None, ""])
    ws.append(["H-010", "金物・部品", "スライド蝶番", "全かぶせ", "個", 480, None, ""])
    ws.append(["", "塗装・仕上", "ウレタン塗装", "", "㎡", 3500, None, "外注単価"])
    for col, width in zip("ABCDEFGH", [10, 12, 24, 16, 6, 10, 10, 20]):
        ws.column_dimensions[col].width = width
    note = wb.create_sheet("説明")
    for line in [
        "■ 原価表の取り込み方",
        "・1 行目を見出しにしてください（「品名」と「原価」は必須）",
        "・列名は 品名/名称、原価/原価単価/仕入単価 なども認識します",
        f"・分類は {' / '.join(l for _, l in Item.Category.choices)} のいずれか（空欄は材料）",
        "・品番があれば品番で、なければ 品名＋規格 で既存の品目を上書きします",
        "・売価が空欄の品目は、見積時に 原価 ÷ (1 − 目標粗利率) で売価を計算します",
    ]:
        note.append([line])
    note.column_dimensions["A"].width = 80
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
