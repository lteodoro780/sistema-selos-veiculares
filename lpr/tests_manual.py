from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from people.models import Person
from vehicles.models import Vehicle

from .models import PlateCorrectionRule, PlatePassage
from .plate_match import resolve_plate


class ManualPlateCorrectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="operador",
            password="senha-forte-teste",
            role="PATRULHANTE",
            is_active=True,
        )
        self.person = Person.objects.create(first_name="João", nome_preferido="JOAO")
        self.vehicle = Vehicle.objects.create(
            proprietario=self.person,
            placa="DEM1C01",
            renavam="12345678901",
            tipo=Vehicle.Tipo.CARRO,
            marca="VW",
            modelo="Gol",
            cor="Branco",
            ano_fabricacao=2020,
            ano_modelo=2020,
        )
        self.passage = PlatePassage.objects.create(
            captured_at=timezone.now(),
            raw_plate="DEM1001",
            plate="DEM1001",
            plate_format=PlatePassage.PlateFormat.MERCOSUL,
            match_method=PlatePassage.MatchMethod.NAO_ENCONTRADA,
            camera_name="CAMERA_DEMO",
            camera_ip="192.0.2.12",
            lane="1",
            camera_direction=PlatePassage.CameraDirection.UNKNOWN,
            movement=PlatePassage.Movement.PASSAGEM,
            pic_name="teste-manual-1",
        )
        self.client.force_login(self.user)

    def test_manual_correction_preserves_raw_and_links_vehicle(self):
        response = self.client.post(
            reverse("lpr:edit", args=[self.passage.pk]),
            {
                "plate": "DEM1C01",
                "movement": "PASSAGEM",
                "learn_rule": "on",
                "note": "Conferida na foto.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.passage.refresh_from_db()
        self.assertEqual(self.passage.raw_plate, "DEM1001")
        self.assertEqual(self.passage.plate, "DEM1C01")
        self.assertEqual(self.passage.vehicle, self.vehicle)
        self.assertEqual(self.passage.person, self.person)
        self.assertEqual(self.passage.match_method, "MANUAL")
        self.assertEqual(self.passage.manual_corrected_by, self.user)
        self.assertIsNotNone(self.passage.manual_corrected_at)
        self.assertFalse(self.passage.matched_automatically)
        self.assertTrue(PlateCorrectionRule.objects.filter(
            raw_plate="DEM1001",
            corrected_plate="DEM1C01",
            camera_ip="192.0.2.12",
            active=True,
        ).exists())

    def test_learned_rule_is_applied_to_future_reading(self):
        PlateCorrectionRule.objects.create(
            raw_plate="DEM1001",
            corrected_plate="DEM1C01",
            camera_ip="192.0.2.12",
            created_by=self.user,
        )
        match = resolve_plate("DEM1001", camera_ip="192.0.2.12")
        self.assertEqual(match.resolved_plate, "DEM1C01")
        self.assertEqual(match.vehicle, self.vehicle)
        self.assertEqual(match.method, "APRENDIDA")

    def test_exact_registered_reading_wins_over_learned_rule(self):
        other = Vehicle.objects.create(
            proprietario=self.person,
            placa="ABC1234",
            renavam="12345678902",
            tipo=Vehicle.Tipo.CARRO,
            marca="Fiat",
            modelo="Uno",
            cor="Prata",
            ano_fabricacao=2015,
            ano_modelo=2015,
        )
        PlateCorrectionRule.objects.create(
            raw_plate="ABC1234",
            corrected_plate="DEM1C01",
            camera_ip="192.0.2.12",
            created_by=self.user,
        )
        match = resolve_plate("ABC1234", camera_ip="192.0.2.12")
        self.assertEqual(match.vehicle, other)
        self.assertEqual(match.method, "EXATA")

    def test_invalid_manual_plate_is_rejected(self):
        response = self.client.post(
            reverse("lpr:edit", args=[self.passage.pk]),
            {
                "plate": "INVALIDA",
                "movement": "PASSAGEM",
                "learn_rule": "on",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe uma placa brasileira válida")
        self.passage.refresh_from_db()
        self.assertEqual(self.passage.plate, "DEM1001")
