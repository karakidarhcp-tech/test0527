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
            "title", "customer", "owner", "phase", "amount",
            "probability", "expected_close_date", "description",
        ]
        widgets = {
            "expected_close_date": DateInput(),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_probability(self):
        value = self.cleaned_data["probability"]
        if not 0 <= value <= 100:
            raise forms.ValidationError("確度は0〜100の範囲で入力してください。")
        return value


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "contact_person", "email", "phone", "address", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class DealSearchForm(forms.Form):
    q = forms.CharField(label="キーワード", required=False,
                        widget=forms.TextInput(attrs={"placeholder": "案件名・顧客名・メモ"}))
    phase = forms.ChoiceField(label="フェーズ", required=False,
                              choices=[("", "すべて"), ("open", "進行中のみ")] + list(Deal.Phase.choices))
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
