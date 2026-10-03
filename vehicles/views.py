from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.utils import timezone
from accounts.access import operator_required as login_required
from django.shortcuts import get_object_or_404, redirect, render

from people.models import Person

from .forms import VehicleForm
from .models import Vehicle


@login_required
def vehicle_person_search(request):
    query = request.GET.get("q", "").strip()
    person_id = request.GET.get("id", "").strip()
    people = Person.objects.filter(is_active=True).annotate(vehicle_count=Count("veiculos", distinct=True))

    if person_id:
        if not person_id.isdigit():
            return JsonResponse({"results": []})
        people = people.filter(pk=int(person_id))
    elif query:
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
                | Q(ramal__icontains=term)
                | Q(identidade_funcional__icontains=term)
            )
        people = people.order_by("-created_at", "nome_preferido", "first_name", "pk")
    else:
        # Sem busca: mostra os cadastros mais recentes, que é o fluxo mais comum
        # logo após cadastrar uma pessoa e partir para o veículo.
        people = people.order_by("-created_at", "-pk")

    now = timezone.now()
    results = []
    for person in people[:12]:
        created = timezone.localtime(person.created_at) if timezone.is_aware(person.created_at) else person.created_at
        results.append({
            "id": person.pk,
            "name": person.nome_exibicao,
            "full_name": person.get_full_name(),
            "rank": person.cargo,
            "section": person.secao,
            "phone": person.telefone,
            "created_label": created.strftime("%d/%m/%Y %H:%M"),
            "recent": (now - person.created_at).total_seconds() <= 7 * 24 * 60 * 60 if timezone.is_aware(person.created_at) else False,
            "vehicle_count": person.vehicle_count,
        })
    return JsonResponse({"results": results})


@login_required
def vehicle_list(request):
    return render(request, "vehicles/list.html", {"vehicles": Vehicle.objects.select_related("proprietario").all()})


@login_required
def vehicle_create(request):
    initial = {}
    if request.method == "GET":
        person_id = request.GET.get("proprietario", "").strip()
        if person_id.isdigit() and Person.objects.filter(pk=int(person_id), is_active=True).exists():
            initial["proprietario"] = int(person_id)
    form = VehicleForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.save()
        messages.success(request, "Veículo cadastrado.")
        return redirect("vehicles:list")
    return render(request, "vehicles/form.html", {"form": form, "title": "Cadastrar veículo"})


@login_required
def vehicle_edit(request, pk):
    obj = get_object_or_404(Vehicle, pk=pk)
    form = VehicleForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.save()
        messages.success(request, "Veículo atualizado.")
        return redirect("vehicles:list")
    return render(request, "vehicles/form.html", {"form": form, "title": "Editar veículo"})
