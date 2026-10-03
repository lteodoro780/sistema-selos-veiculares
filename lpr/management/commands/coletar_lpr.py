import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from seals.models import Seal
from lpr.models import PlatePassage
from lpr.plate_match import normalize_plate, resolve_plate


BODY = (
    '<AfterTime version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    '<picTime>0</picTime>'
    '</AfterTime>'
).encode("utf-8")


def local_name(tag):
    return tag.split("}", 1)[-1]


def child_text(element, name):
    for child in list(element):
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_capture_time(value):
    try:
        naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        return timezone.make_aware(naive, timezone.get_current_timezone())
    except (TypeError, ValueError):
        return timezone.now()


def seal_snapshot(vehicle):
    if not vehicle:
        return "", ""
    try:
        seal = vehicle.selo
    except Seal.DoesNotExist:
        return "", ""
    return seal.numero_serial, seal.status


class CameraClient:
    def __init__(self, ip, username, password):
        self.ip = ip
        self.base = f"http://{ip}"
        manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, self.base, username, password)
        self.opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(manager))

    def fetch_plates(self):
        request = urllib.request.Request(
            self.base + "/ISAPI/Traffic/channels/1/vehicleDetect/plates",
            data=BODY,
            headers={"Content-Type": "application/xml"},
            method="POST",
        )
        with self.opener.open(request, timeout=15) as response:
            return response.read()

    def fetch_image(self, pic_name):
        url = self.base + f"/doc/ui/images/plate/{pic_name}.jpg"
        with self.opener.open(url, timeout=15) as response:
            data = response.read()
        if not data.startswith(b"\xff\xd8\xff"):
            raise ValueError("A câmera não retornou uma imagem JPEG válida.")
        return data


class Command(BaseCommand):
    help = "Coleta placas Hikvision, aplica regras ensinadas manualmente e vínculo conservador antiga/Mercosul."

    def handle(self, *args, **options):
        if os.environ.get("LPR_ENABLED", "false").lower() != "true":
            raise CommandError("Coleta desativada. Configure a câmera e defina LPR_ENABLED=true explicitamente.")
        ip = os.environ.get("LPR_CAM_IP", "").strip()
        username = os.environ.get("LPR_CAM_USER", "").strip()
        password = os.environ.get("LPR_CAM_PASS", "")
        camera_name = os.environ.get("LPR_CAMERA_NAME", "CAMERA_DEMO").strip() or ip
        try:
            interval = max(1.0, float(os.environ.get("LPR_POLL_SECONDS", "2")))
        except ValueError as exc:
            raise CommandError("LPR_POLL_SECONDS inválido.") from exc
        movement_map = {
            "forward": os.environ.get("LPR_FORWARD_MOVEMENT", "PASSAGEM").upper(),
            "reverse": os.environ.get("LPR_REVERSE_MOVEMENT", "PASSAGEM").upper(),
            "unknown": os.environ.get("LPR_UNKNOWN_MOVEMENT", "PASSAGEM").upper(),
        }
        valid_movements = {choice for choice, _ in PlatePassage.Movement.choices}
        if not ip or not username or not password:
            raise CommandError("Defina LPR_CAM_IP, LPR_CAM_USER e LPR_CAM_PASS.")
        if any(value not in valid_movements for value in movement_map.values()):
            raise CommandError("Mapeamento de movimento inválido; use ENTRADA, SAIDA ou PASSAGEM.")

        client = CameraClient(ip, username, password)
        self.stdout.write(self.style.SUCCESS(f"LPR ativo: {camera_name} ({ip}), consulta a cada {interval:g}s."))
        self.stdout.write("Correções manuais aprendidas têm prioridade sobre inferências OCR, mas nunca sobre cadastro exato.")

        while True:
            try:
                xml = client.fetch_plates()
                root = ET.fromstring(xml)
                for element in root.iter():
                    if local_name(element.tag) != "Plate":
                        continue
                    pic_name = child_text(element, "picName")
                    raw_plate = normalize_plate(child_text(element, "plateNumber"))
                    if not pic_name or not raw_plate:
                        continue
                    if PlatePassage.objects.filter(camera_ip=ip, pic_name=pic_name).exists():
                        continue

                    image = None
                    image_error = None
                    try:
                        image = client.fetch_image(pic_name)
                    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                        image_error = exc

                    match = resolve_plate(raw_plate, image_bytes=image, camera_ip=ip)
                    vehicle = match.vehicle
                    person = vehicle.proprietario if vehicle else None

                    direction = (child_text(element, "direction") or "unknown").lower()
                    if direction not in dict(PlatePassage.CameraDirection.choices):
                        direction = "unknown"
                    movement = movement_map.get(direction, movement_map["unknown"])
                    captured_at = parse_capture_time(child_text(element, "captureTime"))
                    serial, seal_status = seal_snapshot(vehicle)

                    try:
                        with transaction.atomic():
                            passage = PlatePassage.objects.create(
                                captured_at=captured_at,
                                raw_plate=match.raw_plate,
                                plate=match.resolved_plate,
                                plate_format=match.plate_format,
                                match_method=match.method,
                                match_note=match.note,
                                vehicle=vehicle,
                                person=person,
                                camera_name=camera_name,
                                camera_ip=ip,
                                lane=child_text(element, "laneNo"),
                                camera_direction=direction,
                                movement=movement,
                                pic_name=pic_name,
                                raw_country=child_text(element, "country"),
                                matched_automatically=bool(vehicle),
                                seal_serial_snapshot=serial,
                                seal_status_snapshot=seal_status,
                            )
                    except IntegrityError:
                        continue

                    if image is not None:
                        try:
                            stamp = captured_at.strftime("%Y/%m/%d")
                            image_plate = match.resolved_plate or match.raw_plate
                            passage.plate_image.save(
                                f"{stamp}/{image_plate}_{pic_name}.jpg", ContentFile(image), save=True
                            )
                        except (OSError, ValueError) as exc:
                            self.stderr.write(f"Imagem {pic_name}: {exc}")
                    elif image_error is not None:
                        self.stderr.write(f"Imagem {pic_name}: {image_error}")

                    linked = person.nome_exibicao if person else "NÃO CADASTRADA"
                    plate_display = match.raw_plate
                    if match.resolved_plate and match.resolved_plate != match.raw_plate:
                        plate_display += f" -> {match.resolved_plate}"
                    self.stdout.write(
                        f"{captured_at:%d/%m/%Y %H:%M:%S} | {plate_display} | "
                        f"{passage.get_plate_format_display()} | {passage.get_match_method_display()} | "
                        f"{passage.get_movement_display()} | {linked}"
                    )
            except ET.ParseError as exc:
                self.stderr.write(f"XML inválido: {exc}")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.stderr.write(f"Falha de comunicação com {ip}: {exc}")
            time.sleep(interval)
