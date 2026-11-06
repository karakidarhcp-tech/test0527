from django import forms
from django.forms import formset_factory, inlineformset_factory

from deals.forms import DateInput
from quotes.forms import QuoteLineForm

from .models import Invoice, InvoiceLine, Payment
from .terms import due_date_for

MONTH_INPUT = forms.DateInput(attrs={"type": "month"}, format="%Y-%m")


class AcceptForm(forms.Form):
    contract_amount = forms.IntegerField(label="確定金額（税抜）", min_value=0)
    accounting_month = forms.DateField(label="計上月", widget=MONTH_INPUT, input_formats=["%Y-%m", "%Y-%m-%d"])
    start_date = forms.DateField(label="着工予定日", required=False, widget=DateInput())
    completion_date = forms.DateField(label="完工予定日", required=False, widget=DateInput())


class ScheduleForm(forms.Form):
    label = forms.CharField(label="区分", max_length=50)
    billing_month = forms.DateField(label="請求月", widget=MONTH_INPUT, input_formats=["%Y-%m", "%Y-%m-%d"])
    amount = forms.IntegerField(label="金額（税抜）", min_value=0)


class BaseScheduleFormSet(forms.BaseFormSet):
    def __init__(self, *args, contract_amount=None, **kwargs):
        self.contract_amount = contract_amount
        super().__init__(*args, **kwargs)

    def clean(self):
        if any(self.errors):
            return
        rows = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not rows:
            raise forms.ValidationError("請求予定を 1 行以上入力してください。")
        total = sum(r["amount"] for r in rows)
        if self.contract_amount is not None and total != self.contract_amount:
            raise forms.ValidationError(
                f"請求予定の合計 {total:,} 円が確定金額 {self.contract_amount:,} 円と一致しません"
                f"（差額 {self.contract_amount - total:+,} 円）。")


ScheduleFormSet = formset_factory(ScheduleForm, formset=BaseScheduleFormSet, extra=0, can_delete=True)


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["title", "issue_date", "due_date", "notes"]
        widgets = {"issue_date": DateInput(), "due_date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cd = super().clean()
        # 請求日だけ変えた場合は、顧客の支払条件から支払期限を計算し直す
        if cd.get("issue_date") and "issue_date" in self.changed_data and "due_date" not in self.changed_data:
            cd["due_date"] = due_date_for(self.instance.deal.customer, cd["issue_date"])
        if cd.get("issue_date") and cd.get("due_date") and cd["due_date"] < cd["issue_date"]:
            self.add_error("due_date", "お支払期限は請求日以降にしてください。")
        return cd


class InvoiceLineForm(QuoteLineForm):
    class Meta(QuoteLineForm.Meta):
        model = InvoiceLine
        fields = ["name", "spec", "quantity", "unit", "unit_price", "tax_rate", "note"]


InvoiceLineFormSet = inlineformset_factory(Invoice, InvoiceLine, form=InvoiceLineForm, extra=0, can_delete=True)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["date", "amount", "method", "note"]
        widgets = {"date": DateInput()}

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v == 0:
            raise forms.ValidationError("0 円は登録できません（返金はマイナスで入力）。")
        return v
