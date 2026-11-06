"""締め日・支払条件から支払期日を計算する"""
import calendar
import datetime


def _day_in_month(year, month, day):
    """day=0 は末日。月の日数を超える日は末日に丸める"""
    last = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last if day == 0 else min(day, last))


def _add_months(year, month, n):
    m = month - 1 + n
    return year + m // 12, m % 12 + 1


def closing_date(date, closing_day):
    """date が属する締め日。例: 20日締めで 11/25 → 12/20、末日締めで 11/25 → 11/30"""
    this_close = _day_in_month(date.year, date.month, closing_day)
    if date <= this_close:
        return this_close
    y, m = _add_months(date.year, date.month, 1)
    return _day_in_month(y, m, closing_day)


def due_date_for(customer, date):
    """請求日 date に対する支払期日（顧客の締め日・支払月・支払日から）"""
    close = closing_date(date, customer.closing_day)
    y, m = _add_months(close.year, close.month, customer.payment_month_offset)
    due = _day_in_month(y, m, customer.payment_day)
    return max(due, close)
