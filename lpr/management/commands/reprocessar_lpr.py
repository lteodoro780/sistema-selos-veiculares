from django.core.management.base import BaseCommand

from seals.models import Seal
from lpr.models import PlatePassage
from lpr.plate_match import resolve_plate


def seal_snapshot(vehicle):
    if not vehicle:
        return "", ""
    try:
        seal = vehicle.selo
    except Seal.DoesNotExist:
        return "", ""
    return seal.numero_serial, seal.status


def passage_image_bytes(passage):
    if not passage.plate_image:
        return None
    try:
        passage.plate_image.open("rb")
        return passage.plate_image.read()
    except (FileNotFoundError, OSError, ValueError):
        return None
    finally:
        try:
            passage.plate_image.close()
        except Exception:
            pass


class Command(BaseCommand):
    help = "Reprocessa LPR não vinculada usando regras manuais, foto, padrão Mercosul e cadastro."

    def handle(self, *args, **options):
        changed = 0
        linked = 0
        review = 0
        learned = 0
        qs = PlatePassage.objects.filter(vehicle__isnull=True).exclude(
            match_method=PlatePassage.MatchMethod.MANUAL
        ).order_by("pk")

        for passage in qs.iterator():
            raw = passage.raw_plate or passage.plate
            match = resolve_plate(
                raw,
                image_bytes=passage_image_bytes(passage),
                camera_ip=str(passage.camera_ip),
            )
            vehicle = match.vehicle
            person = vehicle.proprietario if vehicle else None
            serial, status = seal_snapshot(vehicle)

            fields = {
                "raw_plate": match.raw_plate,
                "plate": match.resolved_plate,
                "plate_format": match.plate_format,
                "match_method": match.method,
                "match_note": match.note,
                "vehicle": vehicle,
                "person": person,
                "matched_automatically": bool(vehicle),
                "seal_serial_snapshot": serial,
                "seal_status_snapshot": status,
            }
            dirty = any(getattr(passage, name) != value for name, value in fields.items())
            if not dirty:
                continue
            for name, value in fields.items():
                setattr(passage, name, value)
            passage.save(update_fields=tuple(fields))
            changed += 1
            if vehicle:
                linked += 1
            if match.method == PlatePassage.MatchMethod.REVISAO:
                review += 1
            if match.method == PlatePassage.MatchMethod.APRENDIDA:
                learned += 1

        self.stdout.write(self.style.SUCCESS(
            "Reprocessamento concluído: "
            f"{changed} alterada(s), {linked} vinculada(s), {learned} por regra aprendida, "
            f"{review} para revisão."
        ))
