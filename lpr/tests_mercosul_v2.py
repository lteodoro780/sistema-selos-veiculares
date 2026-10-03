from io import BytesIO

from django.test import TestCase
from PIL import Image, ImageDraw

from people.models import Person
from vehicles.models import Vehicle

from .plate_match import detect_image_format, resolve_plate


def mercosul_test_image():
    image = Image.new("RGB", (112, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 111, 16), fill=(20, 70, 150))
    out = BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


class MercosulV2Tests(TestCase):
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

    def test_detects_blue_mercosul_band(self):
        self.assertEqual(detect_image_format(mercosul_test_image()), "MERCOSUL")

    def test_exact_old_plate_still_wins(self):
        vehicle = self.vehicle("DEE8382", "10000000001")
        match = resolve_plate("DEE8382", image_bytes=mercosul_test_image())
        self.assertEqual(match.vehicle, vehicle)
        self.assertEqual(match.method, "EXATA")

    def test_qnm_camera_zero_can_match_registered_c_in_fifth_position(self):
        vehicle = self.vehicle("DEM1C01", "10000000002")
        match = resolve_plate("DEM1001", image_bytes=mercosul_test_image())
        self.assertEqual(match.vehicle, vehicle)
        self.assertEqual(match.resolved_plate, "DEM1C01")
        self.assertEqual(match.method, "OCR")
        self.assertEqual(match.plate_format, "MERCOSUL")

    def test_rou_camera_zero_can_match_registered_c_in_fifth_position(self):
        vehicle = self.vehicle("DUM7C07", "10000000003")
        match = resolve_plate("DUM7007", image_bytes=mercosul_test_image())
        self.assertEqual(match.vehicle, vehicle)
        self.assertEqual(match.resolved_plate, "DUM7C07")

    def test_without_blue_band_does_not_turn_valid_old_shape_into_mercosul(self):
        self.vehicle("DEM1C01", "10000000004")
        match = resolve_plate("DEM1001")
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.resolved_plate, "DEM1001")

    def test_unknown_blue_plate_is_classified_mercosul_but_not_invented(self):
        match = resolve_plate("DEM1001", image_bytes=mercosul_test_image())
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.plate_format, "MERCOSUL")
        self.assertEqual(match.raw_plate, "DEM1001")
        self.assertEqual(match.resolved_plate, "DEM1001")
        self.assertIn("não é seguro inventar", match.note)

    def test_two_possible_registered_letters_require_review(self):
        self.vehicle("DEM1C01", "10000000005")
        self.vehicle("DEM1O01", "10000000006")
        match = resolve_plate("DEM1001", image_bytes=mercosul_test_image())
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.method, "REVISAO")

    def test_multiple_arbitrary_errors_are_not_auto_corrected(self):
        self.vehicle("DKJ7H28", "10000000007")
        match = resolve_plate("DKO7826", image_bytes=mercosul_test_image())
        self.assertIsNone(match.vehicle)
        self.assertEqual(match.resolved_plate, "DKO7826")
