from django.test import TestCase

from people.models import Person
from vehicles.models import Vehicle

from .plate_match import raw_variants_for_registered_plate, identify_format, resolve_plate
from .tests_mercosul_v2 import mercosul_test_image


class MercosulPlateMatchTests(TestCase):
    def setUp(self):
        self.person = Person.objects.create(first_name="Teste", nome_preferido="TESTE")

    def vehicle(self, plate, renavam):
        return Vehicle.objects.create(
            proprietario=self.person,
            placa=plate,
            renavam=renavam,
            tipo=Vehicle.Tipo.CARRO,
            marca="Marca",
            modelo="Modelo",
            cor="Branca",
            ano_fabricacao=2024,
            ano_modelo=2024,
        )

    def test_identifies_both_brazilian_formats(self):
        self.assertEqual(identify_format("ABC1234"), "ANTIGA")
        self.assertEqual(identify_format("ABC1D23"), "MERCOSUL")

    def test_exact_match_always_wins(self):
        vehicle = self.vehicle("ABC1023", "00000000001")
        match = resolve_plate("ABC1023", image_bytes=mercosul_test_image())
        self.assertEqual(match.vehicle, vehicle)
        self.assertEqual(match.method, "EXATA")
        self.assertEqual(match.resolved_plate, "ABC1023")

    def test_safe_mercosul_correction_uses_registered_vehicle(self):
        vehicle = self.vehicle("ABC1O23", "00000000002")
        match = resolve_plate("ABC1023", image_bytes=mercosul_test_image())
        self.assertEqual(match.vehicle, vehicle)
        self.assertEqual(match.method, "OCR")
        self.assertEqual(match.resolved_plate, "ABC1O23")
        self.assertIn("0→O", match.note)

    def test_ambiguous_registered_candidates_are_not_linked(self):
        self.vehicle("ABC1023", "00000000003")
        self.vehicle("ABC1O23", "00000000004")
        # I na quarta posição pode virar 1; O na quinta pode ser 0 (antiga)
        # ou permanecer O (Mercosul), produzindo dois cadastros possíveis.
        match = resolve_plate("ABCIO23")
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.method, "REVISAO")

    def test_unknown_plate_is_preserved(self):
        match = resolve_plate("XYZ9A99")
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.raw_plate, "XYZ9A99")
        self.assertEqual(match.resolved_plate, "XYZ9A99")
        self.assertEqual(match.method, "NAO_ENCONTRADA")

    def test_candidate_generator_does_not_guess_unmapped_letters(self):
        details = raw_variants_for_registered_plate("ABC1P23")
        self.assertIn("ABC1P23", details)
        self.assertNotIn("ABC1F23", details)
