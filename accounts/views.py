from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from deals.models import Deal

from .forms import ProfileForm, StaffUserCreationForm, StaffUserUpdateForm

User = get_user_model()


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"

    def get_queryset(self):
        return User.objects.annotate(
            open_count=Count("owned_deals", filter=Q(owned_deals__phase__in=Deal.OPEN_PHASES))
        ).order_by("-is_active", "username")


class UserCreateView(StaffRequiredMixin, CreateView):
    model = User
    form_class = StaffUserCreationForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user_list")

    def form_valid(self, form):
        messages.success(self.request, "ユーザーを作成しました。")
        return super().form_valid(form)


class UserUpdateView(StaffRequiredMixin, UpdateView):
    model = User
    form_class = StaffUserUpdateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user_list")

    def form_valid(self, form):
        # 自分自身の管理者権限・有効フラグは外せないようにする(締め出し防止)
        if form.instance.pk == self.request.user.pk and (
            not form.cleaned_data["is_staff"] or not form.cleaned_data["is_active"]
        ):
            form.add_error(None, "自分自身の管理者権限・有効状態は変更できません。")
            return self.form_invalid(form)
        messages.success(self.request, "ユーザー情報を更新しました。")
        return super().form_valid(form)


@login_required
def user_set_password(request, pk):
    if not request.user.is_staff:
        return redirect("dashboard")
    target = get_object_or_404(User, pk=pk)
    form = SetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if target == request.user:
            update_session_auth_hash(request, target)
        messages.success(request, f"{target.username} のパスワードを再設定しました。")
        return redirect("user_list")
    return render(request, "accounts/password_form.html",
                  {"form": form, "title": f"パスワード再設定: {target.username}"})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "プロフィールを更新しました。")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "パスワードを変更しました。")
        return redirect("profile")
    return render(request, "accounts/password_form.html", {"form": form, "title": "パスワード変更"})
