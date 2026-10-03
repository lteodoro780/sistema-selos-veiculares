from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class OperationsAccessTests(TestCase):
    def test_regular_user_cannot_open_operations(self):
        User.objects.create_user(username="comum", password="SenhaForte123!")
        self.client.login(username="comum", password="SenhaForte123!")
        response = self.client.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_open_operations(self):
        User.objects.create_user(username="staff", password="SenhaForte123!", is_staff=True, role="ADMINISTRADOR")
        self.client.login(username="staff", password="SenhaForte123!")
        response = self.client.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 200)
