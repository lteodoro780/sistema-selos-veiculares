from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.access import operator_required
from seals.models import Seal
from vehicles.models import Vehicle

from .forms import PlatePassageCorrectionForm
from .models import PlateCorrectionRule, PlatePassage
from .plate_match import identify_format, normalize_plate


def seal_snapshot(vehicle):
    if not vehicle:
        return "", ""
    try:
        seal = vehicle.selo
    except Seal.DoesNotExist:
        return "", ""
    return seal.numero_serial, seal.status


@operator_required
def passage_list(request):
    qs = PlatePassage.objects.select_related("vehicle", "person", "manual_corrected_by").all()
    query = request.GET.get("q", "").strip()
    movement = request.GET.get("movimento", "").strip()
    matched = request.GET.get("vinculo", "").strip()
    method = request.GET.get("metodo", "").strip()
    day = request.GET.get("data", "").strip()

    if query:
        qs = qs.filter(
            Q(raw_plate__icontains=query)
            | Q(plate__icontains=query)
            | Q(vehicle__placa__icontains=query)
            | Q(person__nome_preferido__icontains=query)
            | Q(person__first_name__icontains=query)
            | Q(person__last_name__icontains=query)
            | Q(camera_name__icontains=query)
        ).distinct()
    if movement in dict(PlatePassage.Movement.choices):
        qs = qs.filter(movement=movement)
    if matched == "sim":
        qs = qs.filter(vehicle__isnull=False)
    elif matched == "nao":
        qs = qs.filter(vehicle__isnull=True)
    if method in dict(PlatePassage.MatchMethod.choices):
        qs = qs.filter(match_method=method)
    if day:
        try:
            qs = qs.filter(captured_at__date=date.fromisoformat(day))
        except ValueError:
            pass

    params = request.GET.copy()
    params.pop("page", None)
    today = timezone.localdate()
    context = {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")),
        "movements": PlatePassage.Movement.choices,
        "match_methods": PlatePassage.MatchMethod.choices,
        "params": params.urlencode(),
        "total": PlatePassage.objects.count(),
        "today_count": PlatePassage.objects.filter(captured_at__date=today).count(),
        "matched_count": PlatePassage.objects.filter(vehicle__isnull=False).count(),
        "unmatched_count": PlatePassage.objects.filter(vehicle__isnull=True).count(),
        "corrected_count": PlatePassage.objects.filter(match_method=PlatePassage.MatchMethod.OCR).count(),
        "manual_count": PlatePassage.objects.filter(
            match_method__in=(PlatePassage.MatchMethod.MANUAL, PlatePassage.MatchMethod.APRENDIDA)
        ).count(),
        "review_count": PlatePassage.objects.filter(match_method=PlatePassage.MatchMethod.REVISAO).count(),
    }
    return render(request, "lpr/list.html", context)


@operator_required
def passage_edit(request, pk):
    passage = get_object_or_404(
        PlatePassage.objects.select_related("vehicle", "person", "manual_corrected_by"),
        pk=pk,
    )
    raw_plate = normalize_plate(passage.raw_plate or passage.plate)
    existing_rule = PlateCorrectionRule.objects.filter(
        raw_plate=raw_plate,
        camera_ip=str(passage.camera_ip),
        active=True,
    ).first()

    initial = {
        "plate": passage.plate,
        "movement": passage.movement,
        "learn_rule": bool(existing_rule),
        "note": passage.manual_note,
    }
    if request.method == "POST":
        form = PlatePassageCorrectionForm(request.POST)
        if form.is_valid():
            corrected = form.cleaned_data["plate"]
            movement = form.cleaned_data["movement"]
            learn_rule = form.cleaned_data["learn_rule"]
            note = form.cleaned_data["note"].strip()
            vehicle = Vehicle.objects.select_related("proprietario").filter(placa=corrected).first()
            person = vehicle.proprietario if vehicle else None
            serial, seal_status = seal_snapshot(vehicle)

            actor = request.user.nome_exibicao or request.user.username
            detail = f"Correção manual por {actor}: {raw_plate}→{corrected}."
            if vehicle:
                detail += " Placa encontrada no cadastro e vinculada ao veículo."
            else:
                detail += " Placa corrigida ainda não possui veículo cadastrado."

            with transaction.atomic():
                passage.plate = corrected
                passage.plate_format = identify_format(corrected)
                passage.match_method = PlatePassage.MatchMethod.MANUAL
                passage.match_note = detail[:255]
                passage.manual_note = note
                passage.manual_corrected_by = request.user
                passage.manual_corrected_at = timezone.now()
                passage.movement = movement
                passage.vehicle = vehicle
                passage.person = person
                passage.matched_automatically = False
                passage.seal_serial_snapshot = serial
                passage.seal_status_snapshot = seal_status
                passage.save(update_fields=(
                    "plate", "plate_format", "match_method", "match_note",
                    "manual_note", "manual_corrected_by", "manual_corrected_at",
                    "movement", "vehicle", "person", "matched_automatically",
                    "seal_serial_snapshot", "seal_status_snapshot",
                ))

                rule_qs = PlateCorrectionRule.objects.filter(
                    raw_plate=raw_plate,
                    camera_ip=str(passage.camera_ip),
                )
                if learn_rule and raw_plate and corrected != raw_plate:
                    PlateCorrectionRule.objects.update_or_create(
                        raw_plate=raw_plate,
                        camera_ip=str(passage.camera_ip),
                        defaults={
                            "corrected_plate": corrected,
                            "active": True,
                            "created_by": request.user,
                        },
                    )
                else:
                    # Se a placa corrigida voltou a ser igual à leitura original,
                    # não faz sentido manter uma regra de substituição antiga.
                    rule_qs.update(active=False)

            if vehicle:
                messages.success(
                    request,
                    f"Passagem corrigida para {corrected} e vinculada a {person.nome_exibicao}.",
                )
            else:
                messages.success(
                    request,
                    f"Passagem corrigida para {corrected}. Ainda não há veículo cadastrado com essa placa.",
                )
            return redirect("lpr:list")
    else:
        form = PlatePassageCorrectionForm(initial=initial)

    context = {
        "passage": passage,
        "form": form,
        "existing_rule": existing_rule,
        "raw_plate": raw_plate,
    }
    return render(request, "lpr/edit.html", context)


@operator_required
def passage_image(request, pk):
    passage = get_object_or_404(PlatePassage, pk=pk)
    if not passage.plate_image:
        raise Http404
    try:
        passage.plate_image.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(passage.plate_image, content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
