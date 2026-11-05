from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class StaffUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "last_name", "first_name", "email", "is_staff"]
        labels = {"is_staff": "管理者権限"}


class StaffUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "last_name", "first_name", "email", "is_staff", "is_active"]
        labels = {"is_staff": "管理者権限", "is_active": "有効"}
        help_texts = {"is_staff": "ユーザー管理・顧客削除・全案件の削除が可能になります。",
                      "is_active": "無効にするとログインできなくなります(案件データは残ります)。"}


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["last_name", "first_name", "email"]
