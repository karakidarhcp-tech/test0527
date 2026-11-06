from django import forms
from django.contrib.auth import get_user_model

from accounts.utils import display_name

from .models import Customer, Deal

User = get_user_model()


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)


class UserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return display_name(obj)


class DealForm(forms.ModelForm):
    owner = UserChoiceField(
        label="担当者", queryset=User.objects.filter(is_active=True).order_by("username"), required=False
    )

    class Meta:
        model = Deal
        fields = [
            "title", "customer", "owner", "phase", "amount", "probability", "expected_close_date",
            "contract_amount", "accounting_month", "start_date", "completion_date", "site_address",
            "description",
        ]
        widgets = {
            "expected_close_date": DateInput(),
            "start_date": DateInput(),
            "completion_date": DateInput(),
            "accounting_month": forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["accounting_month"].input_formats = ["%Y-%m", "%Y-%m-%d"]
        self.fields["accounting_month"].help_text = "受注した売上を計上する月"

    def clean_probability(self):
        value = self.cleaned_data["probability"]
        if not 0 <= value <= 100:
            raise forms.ValidationError("確度は0〜100の範囲で入力してください。")
        return value


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "honorific", "contact_person", "email", "phone", "postal_code", "address",
                  "closing_day", "payment_month_offset", "payment_day", "notes"]

    def clean(self):
        cd = super().clean()
        for f in ("closing_day", "payment_day"):
            v = cd.get(f)
            if v is not None and v > 28:
                self.add_error(f, "1〜28、または末日の場合は 0 を入力してください。")
        return cd
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class DealSearchForm(forms.Form):
    q = forms.CharField(label="キーワード", required=False,
                        widget=forms.TextInput(attrs={"placeholder": "案件番号・案件名・顧客名"}))
    phase = forms.ChoiceField(label="フェーズ", required=False,
                              choices=[("", "すべて"), ("open", "見積・商談中"), ("won_all", "受注・完工")]
                              + list(Deal.Phase.choices))
    owner = UserChoiceField(label="担当者", required=False, empty_label="すべて",
                            queryset=User.objects.order_by("username"))
    customer = forms.ModelChoiceField(label="顧客", required=False, empty_label="すべて",
                                      queryset=Customer.objects.all())
    close_from = forms.DateField(label="受注予定日(から)", required=False, widget=DateInput())
    close_to = forms.DateField(label="受注予定日(まで)", required=False, widget=DateInput())
    sort = forms.ChoiceField(label="並び順", required=False, choices=[
        ("-updated_at", "更新日(新しい順)"),
        ("expected_close_date", "受注予定日(近い順)"),
        ("-amount", "金額(大きい順)"),
        ("-probability", "確度(高い順)"),
    ])


class CommentForm(forms.Form):
    body = forms.CharField(label="コメント", max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 3, "placeholder": "商談メモ・やり取りを記録"}))


def describe_changes(form, old):
    """保存前の値 old と保存後のインスタンスを比べ「項目: 旧 → 新」の行に整形する
    (フェーズ変更による確度の自動設定なども拾えるよう、フォーム入力ではなく保存結果で比較)"""
    lines = []
    for name, field in form.fields.items():
        before, after = old.get(name), getattr(form.instance, name)
        if before == after:
            continue
        if name == "description":
            lines.append(f"{field.label}を更新")
            continue
        lines.append(f"{field.label}: {_fmt(name, before)} → {_fmt(name, after)}")
    return "\n".join(lines)


def _fmt(name, value):
    if value in (None, ""):
        return "(なし)"
    if name == "phase":
        return Deal.Phase(value).label
    if name == "owner":
        return display_name(value)
    if name == "accounting_month":
        return value.strftime("%Y年%-m月")
    if name in ("amount", "contract_amount"):
        return f"¥{int(value):,}"
    if name == "probability":
        return f"{value}%"
    if hasattr(value, "strftime"):
        return value.strftime("%Y/%m/%d")
    return str(value)
