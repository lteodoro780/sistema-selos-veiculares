from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from people.models import Person
from vehicles.models import Vehicle

from .models import Seal, SealScan


class SealFlowTests(TestCase):
    def setUp(self):
        self.user = Person.objects.create(username="teste", nome_preferido="TESTE")
        self.vehicle = Vehicle.objects.create(
            proprietario=self.user, placa="ABC1D23", renavam="00123456789",
            marca="Teste", modelo="Modelo", cor="Verde", ano_fabricacao=2025,
            ano_modelo=2026, status=Vehicle.Status.APROVADO,
        )
        self.seal = Seal.objects.create(
            veiculo=self.vehicle, status=Seal.Status.ATIVO,
            validade=date.today() + timedelta(days=365),
        )
        self.admin = User.objects.create_user(username="admin", password="SenhaForte123!", is_staff=True, role="ADMINISTRADOR")

    def test_admin_query_registers_scan(self):
        self.client.login(username="admin", password="SenhaForte123!")
        response = self.client.get(reverse("seals:public", args=(self.seal.token_publico,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SealScan.objects.filter(selo=self.seal).count(), 1)

    def test_admin_can_download_qr_and_pdf(self):
        self.client.login(username="admin", password="SenhaForte123!")
        qr = self.client.get(reverse("seals:qr", args=(self.seal.pk,)))
        pdf = self.client.get(reverse("seals:pdf", args=(self.seal.pk,)))
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr["Content-Type"], "image/png")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_staff_can_open_imported_vehicle_qr(self):
        self.client.login(username="admin", password="SenhaForte123!")
        response = self.client.get(reverse("seals:qr", args=(self.seal.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
