import io
import zipfile
from xml.sax.saxutils import escape

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .csv_import import apply_import_package, parse_import_file
from .models import User as AccessUser
from people.models import Person as User
from seals.models import Seal
from vehicles.models import Vehicle


def legacy_row():
    row = [""] * 27
    row[0:12] = ["COLABORADOR", "PESSOA TESTE", "SECAO", "2030", "2024", "MARCA", "MODELO", "PRATA", "ABC-1D23", "1", "", "OK"]
    row[15:27] = ["24709", "ST", "OUTRA PESSOA", "OUTRA SECAO", "2031", "2023", "YAMAHA", "FAZER 150", "PRETA", "DEF-4G56", "", "2"]
    return "\t".join(row).encode("utf-8")


def xlsx_from_sheets(sheets):
    def cell_reference(column, row):
        letters = ""
        column += 1
        while column:
            column, remainder = divmod(column - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row}"

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for index in range(1, len(sheets) + 1))
        archive.writestr("[Content_Types].xml", f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{overrides}</Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        workbook_sheets = "".join(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>' for index, (name, _) in enumerate(sheets, start=1))
        relationships = "".join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(sheets) + 1))
        archive.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>')
        for sheet_index, (_, rows) in enumerate(sheets, start=1):
            xml_rows = []
            for row_number, row in enumerate(rows, start=1):
                cells = []
                for column, value in enumerate(row):
                    if value == "":
                        continue
                    reference = cell_reference(column, row_number)
                    cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
                xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
            archive.writestr(f"xl/worksheets/sheet{sheet_index}.xml", f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    return stream.getvalue()


def xlsx_from_rows(rows):
    return xlsx_from_sheets([("Veículos", rows)])


class CSVImportTests(TestCase):
    def setUp(self):
        self.admin = AccessUser.objects.create_user(username="admin", password="SenhaForte123!", is_staff=True, role="ADMINISTRADOR")

    def test_legacy_tsv_creates_people_and_vehicles(self):
        package = parse_import_file(legacy_row(), "veiculos.tsv")
        self.assertEqual(package["errors"], [])
        self.assertEqual(len(package["people"]), 2)
        self.assertEqual(len(package["vehicles"]), 2)
        self.assertTrue(package["people"][0]["username"].startswith("colaborador_"))
        result = apply_import_package(package)
        self.assertEqual(result["people_created"], 2)
        self.assertEqual(result["vehicles_created"], 2)
        self.assertEqual(Vehicle.objects.filter(tipo=Vehicle.Tipo.MOTO).count(), 1)
        self.assertEqual(result["seals_created"], 1)
        self.assertEqual(Seal.objects.get().numero_serial, "24709")

    def test_reimport_renames_old_imp_username_without_duplicate(self):
        old_user = User.objects.create(
            username="imp_pessoateste_7a227993",
            first_name="Pessoa Teste",
            nome_preferido="PESSOA TESTE",
            secao="SECAO",
        )
        package = parse_import_file(legacy_row(), "veiculos.tsv")
        old_name = package["people"][0]["previous_username"]
        old_user.username = old_name
        old_user.save(update_fields=("username",))
        result = apply_import_package(package)
        old_user.refresh_from_db()
        self.assertEqual(result["people_created"], 1)
        self.assertEqual(result["people_updated"], 1)
        self.assertEqual(old_user.username, old_name)
        self.assertEqual(User.objects.filter(pk=old_user.pk).count(), 1)

    def test_staff_can_preview_upload_without_writing(self):
        self.client.login(username="admin", password="SenhaForte123!")
        upload = SimpleUploadedFile("veiculos.tsv", legacy_row(), content_type="text/tab-separated-values")
        response = self.client.post(reverse("accounts:csv-import"), {"action": "preview", "arquivo": upload})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prévia dos veículos")
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_excel_xlsx_legacy_layout_is_recognized(self):
        row = [""] * 27
        row[0:12] = ["COLABORADOR", "PESSOA EXCEL", "SECAO", "2030", "2024", "MARCA", "MODELO", "PRATA", "ABC-1D23", "1", "", "OK"]
        package = parse_import_file(xlsx_from_rows([row]), "veiculos.xlsx")
        self.assertEqual(package["errors"], [])
        self.assertEqual(package["mode"], "legacy_vehicles_xlsx")
        self.assertEqual(len(package["people"]), 1)
        self.assertEqual(package["vehicles"][0]["placa"], "ABC1D23")

    def test_excel_xlsx_imports_all_vehicle_sheets(self):
        st_row = [""] * 27
        st_row[0:12] = ["COLABORADOR", "PESSOA GRUPO B", "SECAO", "2030", "2024", "MARCA", "MODELO", "PRATA", "AAA-1A11", "1", "", "OK"]
        cb_row = [""] * 27
        cb_row[0:12] = ["COLABORADOR", "PESSOA GRUPO A", "SECAO", "2030", "2023", "MARCA", "MODELO", "AZUL", "BBB-2B22", "1", "", "OK"]
        student_row = [""] * 27
        student_row[16:27] = ["", "PESSOA ALUNO", "CURSO", "2031", "2022", "HONDA", "CG", "PRETA", "CCC-3C33", "", "2"]
        provisional_row = [""] * 27
        provisional_row[0:12] = ["", "", "PESSOA PROVISORIA", "2030", "2024", "MARCA", "MODELO", "BRANCO", "DDD-4D44", "PORTARIA", "", "OK"]
        official_row = [""] * 27
        official_row[0:12] = ["COLABORADOR", "PESSOA GRUPO_C", "2030", "2021", "MARCA", "MODELO", "PRETO", "EEE-5E55", "SETOR DEMO", "", "1", "OK"]
        civil_row = [""] * 29
        civil_row[0:12] = ["", "SC", "PESSOA CIVIL", "2030", "2020", "MARCA", "MODELO", "CINZA", "FFF-6F66", "ADMIN", "", "1"]
        content = xlsx_from_sheets([
            ("GRUPO B", [st_row]), ("PROVISÓRIO", [provisional_row]), ("GRUPO A", [cb_row]),
            ("GRUPO C", [official_row]), ("DEPENDENTE_FUNCIONARIO_CIVIL_E_", [civil_row]), ("ALUNOS", [student_row]),
        ])
        package = parse_import_file(content, "veiculos.xlsx")
        self.assertEqual(package["errors"], [])
        self.assertEqual(len(package["vehicles"]), 6)
        self.assertEqual(len(package["sheets"]), 6)
        classes = {person["classe_funcional"] for person in package["people"]}
        self.assertIn(User.Classe.GRUPO_B, classes)
        self.assertIn(User.Classe.GRUPO_A, classes)
        self.assertIn(User.Classe.GRUPO_C, classes)
        self.assertIn(User.Classe.PRESTADOR, classes)
        self.assertTrue(any(person["cargo"] == "ALUNO" for person in package["people"]))
        self.assertTrue(any(person["cargo"] == "PROVISÓRIO" for person in package["people"]))
        self.assertEqual(sum(1 for vehicle in package["vehicles"] if vehicle["tipo"] == Vehicle.Tipo.MOTO), 1)

    def test_duplicate_seal_numbers_on_different_plates_are_not_linked(self):
        first = [""] * 28
        first[16:28] = ["12345", "COLABORADOR", "PESSOA UM", "SECAO", "2030", "2024", "HONDA", "CG", "PRETA", "AAA-1A11", "", "1"]
        second = [""] * 27
        second[14:27] = ["12345", "COLABORADOR", "PESSOA DOIS", "2030", "2024", "HONDA", "XRE", "AZUL", "BBB-2B22", "SECAO", "1", "", "OK"]
        package = parse_import_file(xlsx_from_sheets([("GRUPO A", [first]), ("GRUPO C", [second])]), "veiculos.xlsx")
        self.assertEqual(package["errors"], [])
        self.assertEqual(sum(1 for item in package["vehicles"] if item.get("seal_number")), 0)
        self.assertTrue(any("placas diferentes" in warning for warning in package["warnings"]))

    def test_phone_and_extension_are_imported_and_merged_for_same_person(self):
        row = [""] * 28
        row[0:12] = ["COLABORADOR", "PESSOA CONTATO", "SECAO", "2030", "2024", "FIAT", "UNO", "PRATA", "AAA-1A11", "1", "00000000002", "OK"]
        row[16:28] = ["24709", "COLABORADOR", "PESSOA CONTATO", "SECAO", "2030", "2024", "HONDA", "CG", "PRETA", "BBB-2B22", "2", "321"]
        package = parse_import_file(xlsx_from_sheets([("GRUPO A", [row])]), "veiculos.xlsx")
        self.assertEqual(package["errors"], [])
        self.assertEqual(len(package["people"]), 1)
        self.assertEqual(package["people"][0]["telefone"], "(00) 00000-0002")
        self.assertEqual(package["people"][0]["ramal"], "321")
        apply_import_package(package)
        person = User.objects.get(username=package["people"][0]["username"])
        self.assertEqual(person.telefone, "(00) 00000-0002")
        self.assertEqual(person.ramal, "321")

    def test_short_value_in_phone_column_is_treated_as_extension(self):
        row = [""] * 27
        row[0:12] = ["COLABORADOR", "PESSOA RAMAL", "SECAO", "2030", "2024", "FIAT", "UNO", "PRATA", "AAA-1A11", "1", "4321", "OK"]
        package = parse_import_file(xlsx_from_sheets([("GRUPO B", [row])]), "veiculos.xlsx")
        self.assertEqual(package["people"][0]["telefone"], "")
        self.assertEqual(package["people"][0]["ramal"], "4321")

    def test_excel_xlsx_people_model_is_recognized(self):
        rows = [
            ["username", "first_name", "role", "ativo"],
            ["teste_excel", "Pessoa", "USUARIO", "1"],
        ]
        package = parse_import_file(xlsx_from_rows(rows), "pessoas.xlsx")
        self.assertEqual(package["errors"], [])
        self.assertEqual(package["mode"], "people_xlsx")
        self.assertEqual(package["people"][0]["username"], "teste_excel")

    def test_regular_user_cannot_access_import(self):
        AccessUser.objects.create_user(username="comum", password="SenhaForte123!")
        self.client.login(username="comum", password="SenhaForte123!")
        response = self.client.get(reverse("accounts:csv-import"))
        self.assertEqual(response.status_code, 302)
