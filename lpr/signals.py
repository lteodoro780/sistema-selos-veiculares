from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from seals.models import Seal
from vehicles.models import Vehicle

from .models import PlatePassage
from .plate_match import raw_variants_for_registered_plate, resolve_plate


def seal_snapshot(vehicle):
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


@receiver(post_save, sender=Vehicle)
def link_previous_unmatched_passages(sender, instance, **kwargs):
    variants = raw_variants_for_registered_plate(instance.placa)
    if not variants:
        return

    passages = PlatePassage.objects.filter(vehicle__isnull=True).exclude(
        match_method=PlatePassage.MatchMethod.MANUAL
    ).filter(Q(raw_plate__in=variants) | Q(raw_plate="", plate__in=variants))

    for passage in passages.iterator():
        raw = passage.raw_plate or passage.plate
        match = resolve_plate(
            raw,
            image_bytes=passage_image_bytes(passage),
            camera_ip=str(passage.camera_ip),
        )
        if not match.vehicle or match.vehicle.pk != instance.pk:
            continue
        serial, status = seal_snapshot(instance)
        passage.raw_plate = match.raw_plate
        passage.plate = match.resolved_plate
        passage.plate_format = match.plate_format
        passage.match_method = match.method
        passage.match_note = match.note
        passage.vehicle = instance
        passage.person = instance.proprietario
        passage.matched_automatically = True
        passage.seal_serial_snapshot = serial
        passage.seal_status_snapshot = status
        passage.save(update_fields=(
            "raw_plate", "plate", "plate_format", "match_method", "match_note",
            "vehicle", "person", "matched_automatically",
            "seal_serial_snapshot", "seal_status_snapshot",
        ))
