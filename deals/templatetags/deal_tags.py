from django import template
from django.utils.html import format_html

from accounts.utils import display_name

register = template.Library()


register.filter("display_name", display_name)


@register.filter
def yen(value):
    try:
        return f"¥{int(value):,}"
    except (TypeError, ValueError):
        return "-"


@register.filter
def man_yen(value):
    """グラフ軸用の短い表記（万円/億円）"""
    v = int(value or 0)
    if v >= 100_000_000:
        return f"{v / 100_000_000:g}億"
    if v >= 10_000:
        return f"{v // 10_000:,}万"
    return f"{v:,}"


@register.simple_tag
def phase_badge(deal_or_value, label=None):
    value = getattr(deal_or_value, "phase", deal_or_value)
    if label is None:
        label = deal_or_value.get_phase_display() if hasattr(deal_or_value, "get_phase_display") else value
    return format_html('<span class="badge phase-{}">{}</span>', value, label)
