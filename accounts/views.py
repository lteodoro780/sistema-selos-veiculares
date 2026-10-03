from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from .access import operator_required as staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render

from documents.models import DriverDocument, VehicleDocument
from operations.models import Occurrence
from seals.models import Seal, SealRequest
from vehicles.models import Vehicle

from .csv_import import apply_import_package, package_preview_counts, parse_import_file
from .forms import CSVImportForm, LoginForm, ProfileForm, RegistrationForm


class PortalLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


def register(request):
    from django.http import HttpResponseNotFound
    return HttpResponseNotFound("O cadastro é realizado pelo administrador na área Pessoas.")


@staff_member_required
def dashboard(request):
    base_qs = Vehicle.objects.select_related("proprietario", "selo").order_by("placa")

    q = (request.GET.get("q") or "").strip()
    type_filter = (request.GET.get("tipo") or "").strip().lower()
    seal_filter = (request.GET.get("selo") or "").strip().lower()

    qs = base_qs
    if q:
        qs = qs.filter(
            Q(placa__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(cor__icontains=q)
            | Q(proprietario__nome_preferido__icontains=q)
            | Q(proprietario__first_name__icontains=q)
            | Q(proprietario__last_name__icontains=q)
            | Q(proprietario__cargo__icontains=q)
            | Q(proprietario__secao__icontains=q)
        ).distinct()

    if type_filter == "moto":
        qs = qs.filter(tipo=Vehicle.Tipo.MOTO)
    elif type_filter == "carro":
        qs = qs.exclude(tipo=Vehicle.Tipo.MOTO)
    else:
        type_filter = ""

    if seal_filter == "com":
        qs = qs.filter(selo__status=Seal.Status.ATIVO)
    elif seal_filter == "sem":
        qs = qs.exclude(selo__status=Seal.Status.ATIVO)
    else:
        seal_filter = ""

    paginator = Paginator(qs, 32)
    page_obj = paginator.get_page(request.GET.get("page"))

    for vehicle in page_obj.object_list:
        try:
            seal = vehicle.selo
        except Seal.DoesNotExist:
            seal = None
        vehicle.dashboard_seal = seal
        vehicle.dashboard_has_active_seal = bool(seal and seal.status == Seal.Status.ATIVO)

    vehicle_total = base_qs.count()
    vehicles_with_active_seal = base_qs.filter(selo__status=Seal.Status.ATIVO).count()

    return render(
        request,
        "accounts/dashboard.html",
        {
            "page_obj": page_obj,
            "q": q,
            "type_filter": type_filter,
            "seal_filter": seal_filter,
            "filtered_count": paginator.count,
            "vehicle_total": vehicle_total,
            "vehicles_with_active_seal": vehicles_with_active_seal,
            "vehicles_without_active_seal": vehicle_total - vehicles_with_active_seal,
        },
    )


@staff_member_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cadastro atualizado.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@staff_member_required
def csv_import(request):
    preview = request.session.get("people_csv_preview")
    errors = []
    form = CSVImportForm()

    if request.method == "POST":
        action = request.POST.get("action", "preview")
        if action == "cancel":
            request.session.pop("people_csv_preview", None)
            messages.info(request, "Importação cancelada.")
            return redirect("accounts:csv-import")
        if action == "confirm":
            package = request.session.get("people_csv_preview") or {}
            if not package.get("people"):
                messages.error(request, "A prévia expirou. Selecione o arquivo novamente.")
            else:
                from django.db import IntegrityError
                try:
                    result = apply_import_package(package, actor=request.user)
                except (ValueError, IntegrityError):
                    messages.error(request, 'Importação cancelada: existe conflito de placa, pessoa ou identificação. Confira a planilha. Nenhum dado foi gravado.')
                    return redirect('accounts:csv-import')
                request.session.pop("people_csv_preview", None)
                messages.success(
                    request,
                    "Importação concluída: "
                    f"{result['people_created']} pessoa(s) criada(s), {result['people_updated']} atualizada(s), "
                    f"{result['vehicles_created']} veículo(s) criado(s), {result['vehicles_updated']} atualizado(s), "
                    f"{result['seals_created']} selo(s) vinculado(s) e {result['seals_updated']} atualizado(s)."
                    + (f" {result['seals_skipped']} selo(s) ambíguo(s) foram ignorado(s)." if result['seals_skipped'] else ""),
                )
            return redirect("accounts:csv-import")

        form = CSVImportForm(request.POST, request.FILES)
        request.session.pop("people_csv_preview", None)
        preview = None
        if form.is_valid():
            upload = form.cleaned_data["arquivo"]
            package = parse_import_file(upload.read(), upload.name)
            errors = package["errors"]
            if not errors:
                request.session["people_csv_preview"] = package
                preview = package

    context = {
        "form": form,
        "preview": preview,
        "people_rows": (preview or {}).get("people", [])[:100],
        "vehicle_rows": (preview or {}).get("vehicles", [])[:100],
        "counts": package_preview_counts(preview) if preview else None,
        "import_mode": (preview or {}).get("mode"),
        "csv_warnings": (preview or {}).get("warnings", []),
        "csv_errors": errors,
    }
    return render(request, "accounts/csv_import.html", context)


@staff_member_required
def csv_template(request):
    content = (
        "username;first_name;last_name;email;cpf;vinculo;classe_funcional;cargo;"
        "nome_preferido;identidade_funcional;organizacao;secao;telefone;ramal;role;ativo\r\n"
        "teste01;Pessoa;Demo;teste01@example.invalid;00000000001;COLABORADOR;GRUPO_B;Colaborador;"
        "PESSOA DEMO;DEMO-001;Organização Demo;Seção de Testes;(00) 00000-0000;1234;USUARIO;1\r\n"
    )
    response = HttpResponse("\ufeff" + content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="modelo-importacao-pessoas.csv"'
    return response
