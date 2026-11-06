from django import forms

from .models import CompanySettings, Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["code", "category", "name", "spec", "unit", "cost", "price", "is_active", "notes"]


class ItemImportForm(forms.Form):
    file = forms.FileField(label="原価表ファイル（.xlsx / .csv）",
                           widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,.xlsm,.csv"}))


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = "__all__"
        widgets = {
            "bank_info": forms.Textarea(attrs={"rows": 3}),
            "quote_terms": forms.Textarea(attrs={"rows": 3}),
            "invoice_terms": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cd = super().clean()
        if (cd.get("deposit_percent") or 0) + (cd.get("interim_percent") or 0) > 100:
            self.add_error("interim_percent", "着工金と中間金の合計は100%以下にしてください。")
        return cd
