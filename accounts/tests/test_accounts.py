from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserManagementTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", password="pw-123456!", is_staff=True)
        self.user = User.objects.create_user("alice", password="pw-123456!")

    def test_non_staff_forbidden(self):
        self.client.login(username="alice", password="pw-123456!")
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_create")).status_code, 403)

    def test_staff_creates_user(self):
        self.client.login(username="boss", password="pw-123456!")
        resp = self.client.post(reverse("user_create"), {
            "username": "newbie", "last_name": "新人", "first_name": "一号", "email": "",
            "password1": "Very-Secret-987", "password2": "Very-Secret-987",
        })
        self.assertRedirects(resp, reverse("user_list"))
        self.assertTrue(self.client.login(username="newbie", password="Very-Secret-987"))

    def test_staff_cannot_lock_self_out(self):
        self.client.login(username="boss", password="pw-123456!")
        self.client.post(reverse("user_update", args=[self.staff.pk]), {
            "username": "boss", "is_active": "on",  # is_staff を外そうとする
        })
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_staff)

    def test_deactivate_user(self):
        self.client.login(username="boss", password="pw-123456!")
        self.client.post(reverse("user_update", args=[self.user.pk]), {"username": "alice"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_login_logout(self):
        resp = self.client.post(reverse("login"), {"username": "alice", "password": "pw-123456!"})
        self.assertRedirects(resp, reverse("dashboard"))
        resp = self.client.post(reverse("logout"))
        self.assertRedirects(resp, reverse("login"))
