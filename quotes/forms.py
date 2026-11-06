from django import forms
from django.forms import inlineformset_factory

from deals.forms import DateInput

from .models import LineMaterial, Quote, QuoteLine


class QuoteForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = ["title", "issue_date", "valid_until", "delivery_terms", "delivery_place", "notes", "internal_memo"]
        widgets = {
            "issue_date": DateInput(), "valid_until": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}), "internal_memo": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cd = super().clean()
        if cd.get("issue_date") and cd.get("valid_until") and cd["valid_until"] < cd["issue_date"]:
            self.add_error("valid_until", "有効期限は発行日以降にしてください。")
        return cd


class QuoteLineForm(forms.ModelForm):
    class Meta:
        model = QuoteLine
        fields = ["name", "spec", "quantity", "unit", "unit_price", "tax_rate", "note", "direct_cost"]
        widgets = {
            "direct_cost": forms.HiddenInput(),
            "quantity": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "unit_price": forms.NumberInput(attrs={"step": "1", "inputmode": "numeric"}),
            "name": forms.TextInput(attrs={"placeholder": "品名"}),
            "spec": forms.TextInput(attrs={"placeholder": "仕様・寸法（例: W1800×D450×H2100）"}),
            "note": forms.TextInput(attrs={"placeholder": "備考（任意）"}),
        }

    def clean_unit_price(self):
        v = self.cleaned_data["unit_price"]
        if v is not None and abs(v) > 10**11:
            raise forms.ValidationError("単価が大きすぎます。")
        return v


QuoteLineFormSet = inlineformset_factory(
    Quote, QuoteLine, form=QuoteLineForm, extra=0, can_delete=True, min_num=0)


class LineCostForm(forms.ModelForm):
    class Meta:
        model = QuoteLine
        fields = ["production_hours", "direct_cost"]
        widgets = {
            "production_hours": forms.NumberInput(attrs={"step": "0.25", "inputmode": "decimal"}),
            "direct_cost": forms.NumberInput(attrs={"step": "1", "inputmode": "decimal"}),
        }

    def clean(self):
        cd = super().clean()
        for f in ("production_hours", "direct_cost"):
            if cd.get(f) is not None and cd[f] < 0:
                self.add_error(f, "マイナスは入力できません。")
        return cd


class LineMaterialForm(forms.ModelForm):
    class Meta:
        model = LineMaterial
        fields = ["item", "name", "spec", "unit", "quantity", "unit_cost"]
        widgets = {
            "item": forms.HiddenInput(),
            "name": forms.TextInput(attrs={"placeholder": "材料名"}),
            "spec": forms.TextInput(attrs={"placeholder": "規格"}),
            "quantity": forms.NumberInput(attrs={"step": "0.001", "inputmode": "decimal"}),
            "unit_cost": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        }

    def clean(self):
        cd = super().clean()
        for f in ("quantity", "unit_cost"):
            if cd.get(f) is not None and cd[f] < 0:
                self.add_error(f, "マイナスは入力できません。")
        return cd


LineMaterialFormSet = inlineformset_factory(
    QuoteLine, LineMaterial, form=LineMaterialForm, extra=0, can_delete=True)
