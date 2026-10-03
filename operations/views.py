import csv

from django.contrib import messages
from accounts.access import operator_required as staff_member_required
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError, OperationalError
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from people.models import Person as User
from documents.models import DriverDocument, VehicleDocument
from seals.models import Seal
from vehicles.models import Vehicle

from .forms import OccurrenceForm, SealLinkForm
from .models import Occurrence


@staff_member_required
def dashboard(request):
    users = User.objects.annotate(
        car_count=Count("veiculos", filter=~Q(veiculos__tipo=Vehicle.Tipo.MOTO), distinct=True),
        motorcycle_count=Count("veiculos", filter=Q(veiculos__tipo=Vehicle.Tipo.MOTO), distinct=True),
        active_seal_count=Count("veiculos__selo", filter=Q(veiculos__selo__status=Seal.Status.ATIVO), distinct=True),
        occurrence_count=Count("ocorrencias", distinct=True),
        open_occurrence_count=Count("ocorrencias", filter=~Q(ocorrencias__status=Occurrence.Status.ENCERRADA), distinct=True),
    ).order_by("nome_preferido", "first_name", "username")
    query = request.GET.get("q", "").strip()
    activity = request.GET.get("activity", "").strip()
    approval = request.GET.get("approval", "").strip()
    user_class = request.GET.get("class", "").strip()
    if query:
        users = users.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(nome_preferido__icontains=query) | Q(cpf__icontains=query) | Q(cargo__icontains=query)
            | Q(organizacao__icontains=query) | Q(secao__icontains=query)
            | Q(telefone__icontains=query) | Q(ramal__icontains=query) | Q(veiculos__placa__icontains=query)
        ).distinct()
    if activity in {"active", "inactive"}:
        users = users.filter(is_active=activity == "active")
    if approval in {"approved", "pending"}:
        users = users.filter(cadastro_aprovado=approval == "approved")
    if user_class in dict(User.Classe.choices):
        users = users.filter(classe_funcional=user_class)
    paginator = Paginator(users, 25)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    context = {
        "people": User.objects.filter(is_active=True).count(),
        "vehicles": Vehicle.objects.count(),
        "active_seals": Seal.objects.filter(status=Seal.Status.ATIVO).count(),
        "open_occurrences": Occurrence.objects.exclude(status=Occurrence.Status.ENCERRADA).count(),
        "by_type": Occurrence.objects.values("tipo").annotate(total=Count("id")).order_by("-total"),
        "users": page,
        "filtered_people": paginator.count,
        "classes": User.Classe.choices,
        "query_params": query_params.urlencode(),
    }
    return render(request, "operations/dashboard.html", context)


@staff_member_required
def user_detail(request, pk):
    person = get_object_or_404(User, pk=pk)
    vehicles = list(Vehicle.objects.filter(proprietario=person).select_related("selo"))
    cars = [vehicle for vehicle in vehicles if vehicle.tipo != Vehicle.Tipo.MOTO]
    motorcycles = [vehicle for vehicle in vehicles if vehicle.tipo == Vehicle.Tipo.MOTO]
    driver_documents = DriverDocument.objects.filter(usuario=person)
    vehicle_documents = VehicleDocument.objects.filter(veiculo__proprietario=person).select_related("veiculo")
    occurrences = Occurrence.objects.filter(proprietario=person).select_related("veiculo", "selo")[:25]
    from lpr.models import PlatePassage
    plate_passages = PlatePassage.objects.filter(person=person).select_related("vehicle")[:50]
    last_plate_passage = plate_passages.first()
    plate_passage_count = PlatePassage.objects.filter(person=person).count()
    cpf = "".join(character for character in (person.cpf or "") if character.isdigit())
    context = {
        "person": person,
        "masked_cpf": f"***.***.***-{cpf[-2:]}" if len(cpf) == 11 else "Não informado",
        "cars": cars,
        "motorcycles": motorcycles,
        "driver_documents": driver_documents,
        "vehicle_documents": vehicle_documents,
        "occurrences": occurrences,
        "car_count": len(cars),
        "motorcycle_count": len(motorcycles),
        "document_count": driver_documents.count() + vehicle_documents.count(),
        "active_seal_count": sum(1 for vehicle in vehicles if hasattr(vehicle, "selo") and vehicle.selo.status == Seal.Status.ATIVO),
        "open_occurrence_count": Occurrence.objects.filter(proprietario=person).exclude(status=Occurrence.Status.ENCERRADA).count(),
        "plate_passages": plate_passages,
        "last_plate_passage": last_plate_passage,
        "plate_passage_count": plate_passage_count,
    }
    return render(request, "operations/user_detail.html", context)


def filtered_occurrences(request):
    qs = Occurrence.objects.select_related("proprietario", "veiculo", "selo", "registrado_por")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        qs = qs.filter(Q(numero__icontains=query) | Q(veiculo__placa__icontains=query) | Q(proprietario__nome_preferido__icontains=query) | Q(local__icontains=query))
    if status in dict(Occurrence.Status.choices):
        qs = qs.filter(status=status)
    return qs


@staff_member_required
def occurrence_list(request):
    return render(request, "operations/list.html", {"occurrences": filtered_occurrences(request), "statuses": Occurrence.Status.choices})


@staff_member_required
def occurrence_people_search(request):
    query = request.GET.get("q", "").strip()
    person_id = request.GET.get("id", "").strip()
    people = User.objects.filter(is_active=True)

    if person_id:
        if not person_id.isdigit():
            return JsonResponse({"results": []})
        people = people.filter(pk=int(person_id))
    else:
        if len(query) < 2:
            return JsonResponse({"results": []})
        for term in query.split():
            people = people.filter(
                Q(nome_preferido__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(cargo__icontains=term)
                | Q(secao__icontains=term)
                | Q(organizacao__icontains=term)
                | Q(telefone__icontains=term)
                | Q(identidade_funcional__icontains=term)
                | Q(cpf__icontains=term)
                | Q(veiculos__placa__icontains=term)
                | Q(veiculos__marca__icontains=term)
                | Q(veiculos__modelo__icontains=term)
            )
        people = people.distinct()

    results = []
    for person in people.order_by("nome_preferido", "first_name", "pk")[:12]:
        vehicles = []
        for vehicle in Vehicle.objects.filter(proprietario=person).select_related("selo").order_by("placa"):
            seal = getattr(vehicle, "selo", None)
            vehicles.append({
                "id": vehicle.pk,
                "plate": vehicle.placa,
                "description": f"{vehicle.marca} {vehicle.modelo}".strip(),
                "type": vehicle.get_tipo_display(),
                "color": vehicle.cor,
                "status": vehicle.get_status_display(),
                "seal_id": str(seal.pk) if seal else "",
                "seal_number": seal.numero_serial if seal else "",
                "seal_status": seal.get_status_display() if seal else "",
            })
        results.append({
            "id": person.pk,
            "name": person.nome_exibicao,
            "full_name": person.get_full_name(),
            "rank": person.cargo,
            "section": person.secao,
            "phone": person.telefone,
            "vehicles": vehicles,
        })
    return JsonResponse({"results": results})


@staff_member_required
def occurrence_create(request):
    form = OccurrenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.registrado_por = request.user
        obj.save()
        messages.success(request, f"Ocorrência {obj.numero} registrada.")
        return redirect("operations:occurrence-list")
    return render(request, "operations/occurrence_form.html", {"form": form, "title": "Registrar ocorrência"})


@staff_member_required
def occurrence_edit(request, pk):
    obj = get_object_or_404(Occurrence, pk=pk)
    form = OccurrenceForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ocorrência atualizada.")
        return redirect("operations:occurrence-list")
    return render(request, "operations/occurrence_form.html", {"form": form, "title": f"Ocorrência {obj.numero}"})


@staff_member_required
def occurrence_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ocorrencias.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(("Número", "Data", "Tipo", "Situação", "Placa", "Proprietário", "Local", "Descrição", "Providências", "Registrado por"))
    for obj in filtered_occurrences(request):
        safe = lambda value: "'" + str(value) if str(value).startswith(("=", "+", "-", "@")) else str(value)
        writer.writerow((obj.numero, obj.data_hora.strftime("%d/%m/%Y %H:%M"), obj.get_tipo_display(), obj.get_status_display(), obj.veiculo.placa, safe(obj.proprietario.nome_exibicao), safe(obj.local), safe(obj.descricao), safe(obj.providencias), obj.registrado_por.username))
    return response


@staff_member_required
def link_seal(request):
    from django.utils import timezone
    form = SealLinkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                data = form.cleaned_data
                person = User.objects.select_for_update().get(pk=data['proprietario'].pk)
                vehicle = Vehicle.objects.select_for_update().get(pk=data['veiculo'].pk)
                if vehicle.proprietario_id != person.pk:
                    raise ValueError('O proprietário do veículo mudou. Reabra o formulário.')
                existing = list(Seal.objects.select_for_update().filter(numero_serial__iexact=data['codigo_selo']))
                if len(existing) > 1:
                    raise ValueError('Há códigos semelhantes no banco. Peça ao administrador para conferir os selos.')
                if existing:
                    if existing[0].veiculo_id != vehicle.pk:
                        raise ValueError('Este código já está vinculado a outro veículo. Nada foi alterado.')
                    messages.info(request, 'O selo já está vinculado a este veículo. Situação, validade e QR Code foram preservados.')
                else:
                    if Seal.objects.filter(veiculo=vehicle).exists():
                        raise ValueError('Este veículo já possui um selo. O vínculo existente foi preservado.')
                    activate = data['ativar_apos_vinculo']
                    if activate and (not person.is_active or vehicle.status != Vehicle.Status.APROVADO or not data['validade'] or data['validade'] < timezone.localdate()):
                        raise ValueError('Os dados mudaram ou não permitem ativação. Confira o veículo, proprietário e validade.')
                    Seal.objects.create(numero_serial=data['codigo_selo'], veiculo=vehicle,
                                        validade=data['validade'], emitido_por=request.user,
                                        status=Seal.Status.ATIVO if activate else Seal.Status.PENDENTE)
                    messages.success(request, 'Selo vinculado ao veículo e ao proprietário. O QR Code está disponível na lista de selos.')
            return redirect('seals:list')
        except (ValueError, IntegrityError, OperationalError) as exc:
            form.add_error(None, str(exc) if isinstance(exc, ValueError) else 'Conflito durante o vínculo. Nenhum selo foi substituído; confira os dados e tente novamente.')
    return render(request, 'operations/link_seal.html', {'form': form})
