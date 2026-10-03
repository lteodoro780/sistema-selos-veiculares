import csv
import hashlib
import io
import posixpath
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from django.db import transaction
from django.utils.text import slugify

from .models import User
from people.models import Person, PersonChange
from seals.models import Seal
from vehicles.models import Vehicle


REQUIRED_COLUMNS = {"username"}
ALLOWED_ROLES = {
    User.Role.USUARIO,
    User.Role.PATRULHANTE,
    User.Role.SUPERVISOR,
}


def _decode_file(content):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o arquivo. Salve-o como CSV UTF-8.")


def _clean_boolean(value):
    return str(value or "1").strip().lower() not in {"0", "false", "nao", "não", "inativo"}


def _contact_digits(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]?\d+", raw):
        try:
            raw = format(Decimal(raw), "f")
        except InvalidOperation:
            pass
    if re.fullmatch(r"\d+\.0+", raw):
        raw = raw.split(".", 1)[0]
    digits = re.sub(r"\D", "", raw)
    return "" if not digits or set(digits) == {"0"} else digits


def _format_phone_digits(digits):
    if len(digits) == 13 and digits.startswith("55"):
        return f"+55 ({digits[2:4]}) {digits[4:9]}-{digits[9:]}"
    if len(digits) == 12 and digits.startswith("55"):
        return f"+55 ({digits[2:4]}) {digits[4:8]}-{digits[8:]}"
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    if len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:]}"
    return digits


def _clean_phone(value):
    return _format_phone_digits(_contact_digits(value))


def _clean_extension(value):
    raw = str(value or "").strip()
    if raw.upper() in {"", "-", "OK", "N/A", "NA", "NÃO", "NAO"}:
        return ""
    digits = _contact_digits(value)
    if digits:
        return _format_phone_digits(digits) if len(digits) >= 8 else digits
    return raw[:30]


def _parse_people_records(records, headers):
    headers = {str(item or "").strip().lower() for item in headers}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return [], [f"Coluna obrigatória ausente: {', '.join(sorted(missing))}."]

    rows = []
    errors = []
    usernames = set()
    cpfs = set()

    for line_number, raw in records:
        row = {str(key or "").strip().lower(): str(value or "").strip() for key, value in raw.items()}
        if not any(row.values()):
            continue

        username = row.get("username", "").lower()
        cpf = re.sub(r"\D", "", row.get("cpf", "")) or None
        role = (row.get("role") or User.Role.USUARIO).upper()
        vinculo = (row.get("vinculo") or User.Vinculo.COLABORADOR).upper()
        classe = (row.get("classe_funcional") or User.Classe.SEM_CLASSE).upper()

        if not username:
            errors.append(f"Linha {line_number}: username vazio.")
            continue
        if username in usernames:
            errors.append(f"Linha {line_number}: username repetido ({username}).")
            continue
        if cpf and cpf in cpfs:
            errors.append(f"Linha {line_number}: CPF repetido no arquivo ({cpf}).")
            continue
        if role not in ALLOWED_ROLES:
            errors.append(f"Linha {line_number}: perfil inválido ou não permitido ({role}).")
            continue
        if vinculo not in dict(User.Vinculo.choices):
            errors.append(f"Linha {line_number}: vínculo inválido ({vinculo}).")
            continue
        if classe not in dict(User.Classe.choices):
            errors.append(f"Linha {line_number}: classe funcional inválida ({classe}).")
            continue
        if cpf:
            owner = Person.objects.filter(cpf=cpf).exclude(username__iexact=username).first()
            if owner:
                errors.append(f"Linha {line_number}: CPF já pertence ao usuário {owner.username}.")
                continue

        usernames.add(username)
        if cpf:
            cpfs.add(cpf)
        rows.append({
            "username": username,
            "first_name": row.get("first_name", ""),
            "last_name": row.get("last_name", ""),
            "email": row.get("email", ""),
            "cpf": cpf,
            "vinculo": vinculo,
            "classe_funcional": classe,
            "cargo": row.get("cargo", ""),
            "nome_preferido": row.get("nome_preferido", ""),
            "identidade_funcional": row.get("identidade_funcional", ""),
            "organizacao": row.get("organizacao", ""),
            "secao": row.get("secao", ""),
            "telefone": _clean_phone(row.get("telefone", "")),
            "ramal": _clean_extension(row.get("ramal", "")),
            "role": role,
            "is_active": _clean_boolean(row.get("ativo")),
        })

    if not rows and not errors:
        errors.append("O arquivo não possui registros para importar.")
    return rows, errors


def parse_people_csv(content):
    text = _decode_file(content)
    if not text.strip():
        return [], ["O arquivo está vazio."]

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    records = enumerate(reader, start=2)
    return _parse_people_records(records, headers)


def _normalized_plate(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _rank_prefix(rank):
    value = slugify(rank or "").replace("-", "")
    replacements = {"1osgt": "1sgt", "2osgt": "2sgt", "3osgt": "3sgt"}
    return replacements.get(value, value)[:12] or "colaborador"


def _generated_username(name, section, rank=""):
    identity = f"{name.strip().upper()}|{section.strip().upper()}"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    base = slugify(name).replace("-", "")[:24] or "pessoa"
    return f"{_rank_prefix(rank)}_{base}_{digest}"


def _legacy_generated_username(name, section):
    identity = f"{name.strip().upper()}|{section.strip().upper()}"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    base = slugify(name).replace("-", "")[:24] or "pessoa"
    return f"imp_{base}_{digest}"


def _generated_renavam(plate):
    number = int(hashlib.sha1(plate.encode("ascii")).hexdigest()[:12], 16) % 10_000_000_000
    return f"9{number:010d}"


def _vehicle_year(value, fallback=2025):
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback, True
    if 1900 <= year <= date.today().year + 1:
        return year, False
    return fallback, True


def _clean_seal_number(value, explicit_column=False):
    """Normaliza apenas números vindos de colunas de selo/lacre ou textos explícitos."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d+(?:\.0+)?", raw):
        return raw.split(".", 1)[0] if explicit_column else ""
    match = re.search(r"(?:SELO|LACRE)\s*[:Nº°.-]*\s*([A-Z0-9][A-Z0-9 ._/-]*)", raw.upper())
    if not match:
        return ""
    number = re.sub(r"[^A-Z0-9]+", "-", match.group(1)).strip("-")
    return number[:24]


def _sheet_blocks(sheet_name):
    """Mapeia os blocos reais de carro e moto de cada aba histórica."""
    key = re.sub(r"[^a-z0-9]", "", slugify(sheet_name or ""))
    standard_car = {
        "kind": Vehicle.Tipo.CARRO, "rank": 0, "name": 1, "section": 2,
        "year": 4, "brand": 5, "model": 6, "color": 7, "plate": 8,
        "phone": 10, "extension": None, "seal": None, "seal_text": (9,),
    }
    profiles = {
        "grupob": (
            standard_car,
            {"kind": Vehicle.Tipo.MOTO, "rank": 16, "name": 17, "section": 18,
             "year": 20, "brand": 21, "model": 22, "color": 23, "plate": 24,
             "phone": 25, "extension": None, "seal": 15, "seal_text": ()},
        ),
        "grupoa": (
            standard_car,
            {"kind": Vehicle.Tipo.MOTO, "rank": 17, "name": 18, "section": 19,
             "year": 21, "brand": 22, "model": 23, "color": 24, "plate": 25,
             "phone": None, "extension": 27, "seal": 16, "seal_text": ()},
        ),
        "grupoc": (
            {"kind": Vehicle.Tipo.CARRO, "rank": 0, "name": 1, "section": 8,
             "year": 3, "brand": 4, "model": 5, "color": 6, "plate": 7,
             "phone": 9, "extension": None, "seal": None, "seal_text": (10,)},
            {"kind": Vehicle.Tipo.MOTO, "rank": 15, "name": 16, "section": 23,
             "year": 18, "brand": 19, "model": 20, "color": 21, "plate": 22,
             "phone": 25, "extension": None, "seal": 14, "seal_text": ()},
        ),
        "dependentefuncionariocivile": (
            {"kind": Vehicle.Tipo.CARRO, "rank": 1, "name": 2, "section": 9,
             "year": 4, "brand": 5, "model": 6, "color": 7, "plate": 8,
             "phone": 10, "extension": None, "seal": 0, "seal_text": ()},
            {"kind": Vehicle.Tipo.MOTO, "rank": 18, "name": 19, "section": 26,
             "year": 21, "brand": 22, "model": 23, "color": 24, "plate": 25,
             "phone": None, "extension": 27, "seal": 17, "seal_text": ()},
        ),
        "alunos": (
            standard_car,
            {"kind": Vehicle.Tipo.MOTO, "rank": 16, "name": 17, "section": 18,
             "year": 20, "brand": 21, "model": 22, "color": 23, "plate": 24,
             "phone": None, "extension": None, "seal": 15, "seal_text": ()},
        ),
        "provisorio": (
            {"kind": Vehicle.Tipo.CARRO, "rank": None, "name": 2, "section": 9,
             "year": 4, "brand": 5, "model": 6, "color": 7, "plate": 8,
             "phone": None, "extension": 10, "seal": None, "seal_text": ()},
            {"kind": Vehicle.Tipo.CARRO, "rank": 2, "name": 3, "section": 4,
             "year": 6, "brand": 7, "model": 8, "color": 9, "plate": 10,
             "phone": 11, "extension": None, "seal": None, "seal_text": ()},
        ),
    }
    return profiles.get(key, (standard_car,))


def _parse_legacy_vehicle_rows(
    source_rows,
    source_name="planilha GRUPO B",
    report_empty=True,
    person_class=User.Classe.GRUPO_B,
    vinculo=User.Vinculo.COLABORADOR,
    default_rank="",
    blocks=None,
):
    """Lê linhas do formato histórico GRUPO B, com carro e moto lado a lado."""
    people = {}
    vehicles = {}
    errors = []
    warnings = []
    ignored_missing = duplicate_plates = adjusted_years = 0

    blocks = blocks or _sheet_blocks("Grupo B")
    required_columns = 1 + max(
        index for block in blocks
        for index in (
            block.get("rank"), block["name"], block["section"], block["year"],
            block["brand"], block["model"], block["color"], block["plate"],
            block.get("phone"), block.get("extension"), block.get("seal"),
            *block.get("seal_text", ()),
        ) if index is not None
    )

    for line_number, row in enumerate(source_rows, start=1):
        if len(row) < required_columns:
            row = list(row) + [""] * (required_columns - len(row))
        for block in blocks:
            name = row[block["name"]].strip()
            plate = _normalized_plate(row[block["plate"]])
            if not name and not plate:
                continue
            if not name or len(plate) != 7:
                ignored_missing += 1
                continue
            section = row[block["section"]].strip()
            rank = row[block["rank"]].strip() if block.get("rank") is not None else ""
            rank = rank or default_rank
            username = _generated_username(name, section, rank)
            year, adjusted = _vehicle_year(row[block["year"]])
            adjusted_years += int(adjusted)
            seal_number = ""
            if block.get("seal") is not None:
                seal_number = _clean_seal_number(row[block["seal"]], explicit_column=True)
            if not seal_number:
                for index in block.get("seal_text", ()):
                    seal_number = _clean_seal_number(row[index])
                    if seal_number:
                        break
            phone_value = _clean_phone(row[block["phone"]]) if block.get("phone") is not None else ""
            extension_value = _clean_extension(row[block["extension"]]) if block.get("extension") is not None else ""
            if phone_value and len(_contact_digits(phone_value)) <= 5:
                extension_value = extension_value or _clean_extension(phone_value)
                phone_value = ""
            if plate in vehicles:
                duplicate_plates += 1
                if seal_number and not vehicles[plate].get("seal_number"):
                    vehicles[plate]["seal_number"] = seal_number
                continue
            person = {
                "username": username,
                "previous_username": _legacy_generated_username(name, section),
                "first_name": name.title(),
                "last_name": "",
                "email": "",
                "cpf": None,
                "vinculo": vinculo,
                "classe_funcional": person_class,
                "cargo": rank,
                "nome_preferido": name.upper(),
                "identidade_funcional": "",
                "organizacao": "",
                "secao": section,
                "telefone": phone_value,
                "ramal": extension_value,
                "role": User.Role.USUARIO,
                "is_active": True,
                "cadastro_aprovado": True,
            }
            if username in people:
                if not people[username].get("telefone") and person["telefone"]:
                    people[username]["telefone"] = person["telefone"]
                if not people[username].get("ramal") and person["ramal"]:
                    people[username]["ramal"] = person["ramal"]
            else:
                people[username] = person
            vehicles[plate] = {
                "owner_username": username,
                "placa": plate,
                "renavam": _generated_renavam(plate),
                "chassi": "",
                "tipo": block["kind"],
                "marca": row[block["brand"]].strip() or "Não informada",
                "modelo": row[block["model"]].strip() or "Não informado",
                "cor": row[block["color"]].strip() or "Não informada",
                "ano_fabricacao": year,
                "ano_modelo": year,
                "status": Vehicle.Status.APROVADO,
                "motivo_status": f"Importado da {source_name}.",
                "seal_number": seal_number,
            }

    if ignored_missing:
        warnings.append(f"{ignored_missing} bloco(s) sem nome ou placa válida foram ignorados.")
    if duplicate_plates:
        warnings.append(f"{duplicate_plates} placa(s) repetida(s) foram mantidas apenas uma vez.")
    if adjusted_years:
        warnings.append(f"{adjusted_years} veículo(s) sem ano válido receberam o ano de referência 2025.")
    if not vehicles and not errors and report_empty:
        errors.append("Nenhum veículo válido foi encontrado no formato GRUPO B.")

    return {
        "mode": "legacy_vehicles",
        "people": list(people.values()),
        "vehicles": list(vehicles.values()),
        "errors": errors,
        "warnings": warnings,
    }


def parse_legacy_vehicle_tsv(content):
    """Lê a planilha histórica GRUPO B, com carro e moto lado a lado."""
    text = _decode_file(content)
    source_rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    return _parse_legacy_vehicle_rows(source_rows)


def _sheet_profile(sheet_name):
    key = slugify(sheet_name or "").replace("-", "")
    if "grupob" in key:
        return User.Classe.GRUPO_B, User.Vinculo.COLABORADOR, "GRUPO B"
    if "grupoa" in key:
        return User.Classe.GRUPO_A, User.Vinculo.COLABORADOR, "GRUPO A"
    if key in {"grupoc", "grupoc", "grupoc"} or key.startswith("grupoc"):
        return User.Classe.GRUPO_C, User.Vinculo.COLABORADOR, "GRUPO C"
    if "civil" in key or "dependente" in key:
        return User.Classe.PRESTADOR, User.Vinculo.PRESTADOR, "PRESTADOR"
    if "aluno" in key:
        return User.Classe.SEM_CLASSE, User.Vinculo.COLABORADOR, "ALUNO"
    if "provisorio" in key:
        return User.Classe.SEM_CLASSE, User.Vinculo.COLABORADOR, "PROVISÓRIO"
    return User.Classe.SEM_CLASSE, User.Vinculo.OUTRO, ""


def _column_index(cell_reference):
    letters = re.match(r"[A-Z]+", str(cell_reference or "").upper())
    if not letters:
        return 0
    index = 0
    for letter in letters.group(0):
        index = index * 26 + ord(letter) - 64
    return index - 1


def _safe_xlsx_members(archive):
    members = archive.infolist()
    if len(members) > 1000 or sum(item.file_size for item in members) > 50 * 1024 * 1024:
        raise ValueError("A planilha Excel é muito grande ou possui uma estrutura inválida.")
    return {item.filename for item in members}


def _xlsx_rows(content):
    """Extrai valores básicos de todas as abas XLSX usando apenas a biblioteca padrão."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("O arquivo Excel está corrompido ou não é um .xlsx válido.") from exc

    with archive:
        members = _safe_xlsx_members(archive)
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(members):
            raise ValueError("O arquivo não possui a estrutura esperada de uma planilha Excel.")

        shared_strings = []
        if "xl/sharedStrings.xml" in members:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("{*}si"):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//{*}t")))

        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib.get("Id"): rel.attrib.get("Target", "")
            for rel in relationships.findall("{*}Relationship")
        }
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = []
        for sheet in workbook.findall(".//{*}sheet"):
            name = sheet.attrib.get("name", "Planilha")
            relation_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = targets.get(relation_id, "")
            if not target:
                continue
            if target.startswith("/"):
                path = target.lstrip("/")
            else:
                path = posixpath.normpath(posixpath.join("xl", target))
            if path not in members:
                continue

            root = ElementTree.fromstring(archive.read(path))
            rows = []
            for row_node in root.findall(".//{*}sheetData/{*}row"):
                values = []
                for cell in row_node.findall("{*}c"):
                    column = _column_index(cell.attrib.get("r"))
                    while len(values) <= column:
                        values.append("")
                    cell_type = cell.attrib.get("t", "")
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
                    else:
                        value_node = cell.find("{*}v")
                        value = value_node.text if value_node is not None else ""
                        if cell_type == "s" and value:
                            try:
                                value = shared_strings[int(value)]
                            except (IndexError, ValueError):
                                value = ""
                        elif cell_type == "b":
                            value = "1" if value == "1" else "0"
                    values[column] = str(value or "").strip()
                while values and values[-1] == "":
                    values.pop()
                rows.append(values)
            sheets.append((name, rows))
        return sheets


def parse_excel_xlsx(content):
    try:
        sheets = _xlsx_rows(content)
    except (ValueError, ElementTree.ParseError) as exc:
        return {"mode": "xlsx", "people": [], "vehicles": [], "errors": [str(exc)], "warnings": []}

    combined_people = {}
    combined_vehicles = {}
    combined_warnings = []
    imported_sheets = []
    duplicate_plates = 0
    for sheet_name, rows in sheets:
        person_class, vinculo, default_rank = _sheet_profile(sheet_name)
        package = _parse_legacy_vehicle_rows(
            rows,
            source_name=f"aba “{sheet_name}”",
            report_empty=False,
            person_class=person_class,
            vinculo=vinculo,
            default_rank=default_rank,
            blocks=_sheet_blocks(sheet_name),
        )
        if not package["vehicles"]:
            continue
        imported_sheets.append(f"{sheet_name} ({len(package['vehicles'])} veículo(s))")
        for warning in package["warnings"]:
            combined_warnings.append(f"Aba “{sheet_name}”: {warning}")
        for person in package["people"]:
            existing_person = combined_people.get(person["username"])
            if existing_person:
                if not existing_person.get("telefone") and person.get("telefone"):
                    existing_person["telefone"] = person["telefone"]
                if not existing_person.get("ramal") and person.get("ramal"):
                    existing_person["ramal"] = person["ramal"]
            else:
                combined_people[person["username"]] = person
        for vehicle in package["vehicles"]:
            if vehicle["placa"] in combined_vehicles:
                duplicate_plates += 1
                if vehicle.get("seal_number") and not combined_vehicles[vehicle["placa"]].get("seal_number"):
                    combined_vehicles[vehicle["placa"]]["seal_number"] = vehicle["seal_number"]
                continue
            combined_vehicles[vehicle["placa"]] = vehicle

    if combined_vehicles:
        seal_plates = {}
        conflicting_seals = set()
        for vehicle in combined_vehicles.values():
            seal_number = vehicle.get("seal_number")
            if not seal_number:
                continue
            existing_plate = seal_plates.setdefault(seal_number, vehicle["placa"])
            if existing_plate != vehicle["placa"]:
                conflicting_seals.add(seal_number)
        if conflicting_seals:
            affected = 0
            for vehicle in combined_vehicles.values():
                if vehicle.get("seal_number") in conflicting_seals:
                    vehicle["seal_number"] = ""
                    affected += 1
            combined_warnings.append(
                f"{affected} veículo(s) ficaram sem vínculo automático porque "
                f"{len(conflicting_seals)} número(s) de selo aparecem em placas diferentes."
            )
        combined_warnings.insert(0, "Abas importadas: " + "; ".join(imported_sheets) + ".")
        if duplicate_plates:
            combined_warnings.append(
                f"{duplicate_plates} placa(s) repetida(s) entre abas foram mantidas apenas uma vez."
            )
        return {
            "mode": "legacy_vehicles_xlsx",
            "people": list(combined_people.values()),
            "vehicles": list(combined_vehicles.values()),
            "errors": [],
            "warnings": combined_warnings,
            "sheets": imported_sheets,
        }

    for sheet_name, rows in sheets:
        for header_index, headers in enumerate(rows):
            normalized_headers = [str(value or "").strip().lower() for value in headers]
            if "username" not in normalized_headers:
                continue
            records = []
            for row_number, values in enumerate(rows[header_index + 1:], start=header_index + 2):
                padded = values + [""] * max(0, len(headers) - len(values))
                records.append((row_number, dict(zip(headers, padded))))
            people, errors = _parse_people_records(records, headers)
            return {
                "mode": "people_xlsx",
                "people": people,
                "vehicles": [],
                "errors": errors,
                "warnings": [f"Dados reconhecidos na aba “{sheet_name}” do arquivo Excel."],
            }

    return {
        "mode": "xlsx",
        "people": [],
        "vehicles": [],
        "errors": [
            "Nenhuma aba compatível foi encontrada. Use o modelo com a coluna username "
            "ou a planilha histórica GRUPO B com os blocos de carro e moto."
        ],
        "warnings": [],
    }


def parse_import_file(content, filename=""):
    if filename.lower().endswith(".xlsx"):
        return parse_excel_xlsx(content)
    text = _decode_file(content)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    first_cells = first_line.split("\t")
    is_legacy = filename.lower().endswith(".tsv") and len(first_cells) >= 27 and first_cells[0].strip().lower() != "username"
    if is_legacy:
        return parse_legacy_vehicle_tsv(content)
    rows, errors = parse_people_csv(content)
    return {"mode": "people", "people": rows, "vehicles": [], "errors": errors, "warnings": []}


def preview_counts(rows):
    candidates = [value for row in rows for value in (row.get("username"), row.get("previous_username")) if value]
    existing = {name.lower() for name in Person.objects.filter(username__in=candidates).values_list("username", flat=True)}
    updated = sum(
        1 for row in rows
        if row["username"].lower() in existing or str(row.get("previous_username") or "").lower() in existing
    )
    return {"total": len(rows), "created": len(rows) - updated, "updated": updated}


def package_preview_counts(package):
    people = preview_counts(package.get("people", []))
    plates = [row["placa"] for row in package.get("vehicles", [])]
    existing_plates = set(Vehicle.objects.filter(placa__in=plates).values_list("placa", flat=True))
    updated_vehicles = sum(1 for plate in plates if plate in existing_plates)
    seal_rows = [row for row in package.get("vehicles", []) if row.get("seal_number")]
    created_seals = updated_seals = skipped_seals = 0
    for row in seal_rows:
        if Seal.objects.filter(numero_serial=row["seal_number"]).exclude(veiculo__placa=row["placa"]).exists():
            skipped_seals += 1
        elif Seal.objects.filter(veiculo__placa=row["placa"]).exists():
            updated_seals += 1
        else:
            created_seals += 1
    return {
        "people_total": people["total"],
        "people_created": people["created"],
        "people_updated": people["updated"],
        "vehicles_total": len(plates),
        "vehicles_created": len(plates) - updated_vehicles,
        "vehicles_updated": updated_vehicles,
        "seals_total": len(seal_rows),
        "seals_created": created_seals,
        "seals_updated": updated_seals,
        "seals_skipped": skipped_seals,
    }


@transaction.atomic
def apply_people_rows(rows, actor=None):
    created = updated = 0
    from people.forms import EDIT_FIELDS
    for row in rows:
        person = Person.objects.filter(username__iexact=row['username']).first()
        if person is None and row.get('previous_username'):
            person = Person.objects.filter(username__iexact=row['previous_username']).first()
        if person is None and row.get('cpf'):
            person = Person.objects.filter(cpf=row['cpf']).first()
        new = person is None
        if new:
            person = Person(username=row['username'])
        changes = {}
        for field in EDIT_FIELDS:
            value = row.get(field)
            old = getattr(person, field)
            if value and (new or not old or field == 'classe_funcional' and old == 'SEM_CLASSE'):
                if old != value:
                    changes[field] = {'before': old, 'after': value}
                    setattr(person, field, value)
        if changes or new:
            person.review_status = Person.Review.PENDING
            person.reviewed_at = None
            person.reviewed_by = None
            person.save()
            PersonChange.objects.create(person=person, actor=actor, source='Planilha de cadastro', changes=changes)
        row['username'] = person.username
        if new:
            created += 1
        else:
            updated += 1
    return {'created': created, 'updated': updated, 'total': created + updated}


@transaction.atomic
def apply_import_package(package, actor=None):
    # Mapeia as referências antes da conciliação por CPF ou importação antiga.
    rows = package.get("people", [])
    original_names = [row['username'] for row in rows]
    people_result = apply_people_rows(rows, actor=actor)
    names = {old: row['username'] for old, row in zip(original_names, rows)}
    vehicle_created = vehicle_updated = 0
    for row in package.get("vehicles", []):
        owner = Person.objects.get(username=names.get(row["owner_username"], row["owner_username"]))
        defaults = {
            key: value for key, value in row.items()
            if key not in {"owner_username", "placa", "seal_number"}
        }
        defaults["proprietario"] = owner
        existing = Vehicle.objects.filter(placa=row["placa"]).first()
        if existing and existing.proprietario_id != owner.pk:
            raise ValueError(f"Placa {row['placa']} vinculada a outra pessoa. Confira antes de importar.")
        if existing:
            # Reimportar uma lista não altera avaliações ou dados já conferidos.
            was_created = False
        else:
            Vehicle.objects.create(placa=row['placa'], **defaults)
            was_created = True
        if was_created:
            vehicle_created += 1
        else:
            vehicle_updated += 1
    seal_created = seal_updated = seal_skipped = 0
    for row in package.get("vehicles", []):
        seal_number = row.get("seal_number")
        if not seal_number:
            continue
        vehicle = Vehicle.objects.get(placa=row["placa"])
        serial_owner = Seal.objects.filter(numero_serial=seal_number).exclude(veiculo=vehicle).first()
        if serial_owner:
            seal_skipped += 1
            continue
        seal = Seal.objects.filter(veiculo=vehicle).first()
        if seal:
            if seal.numero_serial != seal_number:
                seal_skipped += 1
                continue
            seal.numero_serial = seal_number
            if actor and not seal.emitido_por_id:
                seal.emitido_por = actor
            seal.save(update_fields=("numero_serial", "emitido_por", "atualizado_em"))
            seal_updated += 1
        else:
            Seal.objects.create(
                veiculo=vehicle,
                numero_serial=seal_number,
                status=Seal.Status.ATIVO,
                emitido_por=actor,
            )
            seal_created += 1
    return {
        "people_created": people_result["created"],
        "people_updated": people_result["updated"],
        "vehicles_created": vehicle_created,
        "vehicles_updated": vehicle_updated,
        "seals_created": seal_created,
        "seals_updated": seal_updated,
        "seals_skipped": seal_skipped,
    }
