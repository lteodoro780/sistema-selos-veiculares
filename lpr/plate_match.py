from dataclasses import dataclass
from io import BytesIO
import re

from vehicles.models import Vehicle

from .models import PlateCorrectionRule


# Confusões clássicas de OCR. Não tentamos adivinhar trocas arbitrárias.
KNOWN_PAIRS = {
    frozenset(("0", "O")),
    frozenset(("1", "I")),
    frozenset(("2", "Z")),
    frozenset(("5", "S")),
    frozenset(("6", "G")),
    frozenset(("8", "B")),
}


@dataclass(frozen=True)
class PlateMatch:
    raw_plate: str
    resolved_plate: str
    vehicle: Vehicle | None
    method: str
    plate_format: str
    note: str = ""


def normalize_plate(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def identify_format(value):
    value = normalize_plate(value)
    if re.fullmatch(r"[A-Z]{3}[0-9]{4}", value):
        return "ANTIGA"
    if re.fullmatch(r"[A-Z]{3}[0-9][A-Z][0-9]{2}", value):
        return "MERCOSUL"
    return "DESCONHECIDA"


def detect_image_format(image_bytes):
    """Retorna MERCOSUL quando a faixa azul superior é detectada com confiança."""
    if not image_bytes:
        return None
    try:
        from PIL import Image

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        if image.width < 20 or image.height < 12:
            return None
        image.thumbnail((224, 128))
        x0 = max(0, int(image.width * 0.05))
        x1 = min(image.width, int(image.width * 0.95))
        y1 = max(2, int(image.height * 0.34))
        pixels = list(image.crop((x0, 0, x1, y1)).getdata())
        if not pixels:
            return None

        blue = 0
        blue_minus_red = 0.0
        for red, green, value_blue in pixels:
            blue_minus_red += value_blue - red
            if (
                value_blue >= 45
                and value_blue >= red + 12
                and value_blue >= green + 6
                and max(red, green, value_blue) - min(red, green, value_blue) >= 18
            ):
                blue += 1

        ratio = blue / len(pixels)
        mean_blue_advantage = blue_minus_red / len(pixels)
        if ratio >= 0.20 and mean_blue_advantage >= 5.0:
            return "MERCOSUL"
    except Exception:
        return None
    return None


def _manual_rule(raw_plate, camera_ip):
    qs = PlateCorrectionRule.objects.filter(raw_plate=raw_plate, active=True)
    if camera_ip:
        scoped = qs.filter(camera_ip=str(camera_ip)).order_by("-updated_at").first()
        if scoped:
            return scoped
    return qs.filter(camera_ip="").order_by("-updated_at").first()


def _known_pair(a, b):
    return frozenset((a, b)) in KNOWN_PAIRS


def _compare_registered(raw_plate, registered_plate, image_hint):
    raw_plate = normalize_plate(raw_plate)
    registered_plate = normalize_plate(registered_plate)
    if len(raw_plate) != 7 or len(registered_plate) != 7:
        return None

    registered_format = identify_format(registered_plate)
    if registered_format == "DESCONHECIDA":
        return None

    raw_format = identify_format(raw_plate)

    if image_hint == "MERCOSUL" and registered_format != "MERCOSUL":
        return None

    if raw_format == "ANTIGA" and registered_format == "MERCOSUL" and image_hint != "MERCOSUL":
        return None

    corrections = []
    score = 0
    generic_mercosul = 0

    for index, (read_char, reg_char) in enumerate(zip(raw_plate, registered_plate)):
        if read_char == reg_char:
            continue

        if _known_pair(read_char, reg_char):
            corrections.append((index + 1, read_char, reg_char, "confusão OCR conhecida"))
            score += 1
            continue

        if (
            registered_format == "MERCOSUL"
            and index == 4
            and read_char.isdigit()
            and reg_char.isalpha()
            and image_hint == "MERCOSUL"
        ):
            corrections.append((index + 1, read_char, reg_char, "5ª posição Mercosul"))
            score += 2
            generic_mercosul += 1
            continue

        return None

    if not corrections or len(corrections) > 2 or generic_mercosul > 1 or score > 3:
        return None

    return score, corrections


def _format_corrections(corrections):
    return ", ".join(
        f"posição {position}: {before}→{after} ({reason})"
        for position, before, after, reason in corrections
    )


def resolve_plate(raw_value, image_bytes=None, camera_ip=None):
    raw_plate = normalize_plate(raw_value)
    if not raw_plate:
        return PlateMatch("", "", None, "NAO_ENCONTRADA", "DESCONHECIDA", "Leitura vazia.")

    image_hint = detect_image_format(image_bytes)

    # Cadastro exato sempre vence inclusive sobre uma regra ensinada anteriormente.
    exact = Vehicle.objects.select_related("proprietario").filter(placa=raw_plate).first()
    if exact:
        return PlateMatch(
            raw_plate=raw_plate,
            resolved_plate=exact.placa,
            vehicle=exact,
            method="EXATA",
            plate_format=identify_format(exact.placa),
            note="Correspondência exata com o cadastro.",
        )

    # Uma correção explicitamente ensinada pelo operador tem prioridade sobre
    # inferências OCR. A leitura original continua preservada em raw_plate.
    rule = _manual_rule(raw_plate, camera_ip)
    if rule:
        corrected = normalize_plate(rule.corrected_plate)
        vehicle = Vehicle.objects.select_related("proprietario").filter(placa=corrected).first()
        scope = f" para a câmera {rule.camera_ip}" if rule.camera_ip else ""
        return PlateMatch(
            raw_plate=raw_plate,
            resolved_plate=corrected or raw_plate,
            vehicle=vehicle,
            method="APRENDIDA",
            plate_format=identify_format(corrected),
            note=(f"Aplicada regra manual aprendida{scope}: {raw_plate}→{corrected}."[:255]),
        )

    compatible = []
    for vehicle in Vehicle.objects.select_related("proprietario").exclude(placa=""):
        result = _compare_registered(raw_plate, vehicle.placa, image_hint)
        if result is None:
            continue
        score, corrections = result
        compatible.append((score, len(corrections), vehicle, corrections))

    if compatible:
        compatible.sort(key=lambda item: (item[0], item[1], item[2].placa))
        # Uma pontuação menor não elimina outro cadastro plausível.
        # Com mais de um veículo compatível, o operador precisa revisar.
        best = compatible

        if len(best) == 1:
            _, _, vehicle, corrections = best[0]
            note = "Correção OCR vinculada a um único veículo cadastrado"
            if image_hint == "MERCOSUL":
                note += "; foto compatível com placa Mercosul"
            correction_text = _format_corrections(corrections)
            if correction_text:
                note += f" ({correction_text})"
            note += "."
            return PlateMatch(
                raw_plate=raw_plate,
                resolved_plate=vehicle.placa,
                vehicle=vehicle,
                method="OCR",
                plate_format=identify_format(vehicle.placa),
                note=note[:255],
            )

        candidates = ", ".join(sorted(item[2].placa for item in best)[:6])
        return PlateMatch(
            raw_plate=raw_plate,
            resolved_plate=raw_plate,
            vehicle=None,
            method="REVISAO",
            plate_format=image_hint or identify_format(raw_plate),
            note=f"Mais de um veículo cadastrado é compatível com a leitura: {candidates}."[:255],
        )

    raw_format = identify_format(raw_plate)
    if image_hint == "MERCOSUL":
        if raw_format == "MERCOSUL":
            note = "Foto compatível com placa Mercosul; nenhum veículo cadastrado corresponde à leitura."
        else:
            note = (
                "Foto compatível com placa Mercosul, mas a leitura da câmera não respeita o formato "
                "Mercosul. Leitura original preservada; sem cadastro compatível não é seguro inventar caracteres."
            )
        return PlateMatch(
            raw_plate=raw_plate,
            resolved_plate=raw_plate,
            vehicle=None,
            method="NAO_ENCONTRADA",
            plate_format="MERCOSUL",
            note=note[:255],
        )

    return PlateMatch(
        raw_plate=raw_plate,
        resolved_plate=raw_plate,
        vehicle=None,
        method="NAO_ENCONTRADA",
        plate_format=raw_format,
        note="Nenhum veículo cadastrado corresponde à leitura com segurança.",
    )


def raw_variants_for_registered_plate(plate):
    plate = normalize_plate(plate)
    if len(plate) != 7:
        return {plate} if plate else set()

    format_name = identify_format(plate)
    variants = {""}
    for index, character in enumerate(plate):
        choices = {character}
        for pair in KNOWN_PAIRS:
            if character in pair:
                choices.update(pair)
        if format_name == "MERCOSUL" and index == 4:
            choices.update("0123456789")
        variants = {prefix + choice for prefix in variants for choice in choices}
        if len(variants) > 5000:
            break
    return variants
