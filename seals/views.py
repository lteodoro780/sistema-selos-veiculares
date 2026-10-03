from datetime import timedelta
from io import BytesIO

import qrcode
from django.contrib import messages
from accounts.access import operator_required as login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import SealRequestForm
from .models import Seal, SealRequest, SealScan
from .pdf_generator import generate_seal_pdf
from .validation import parse_seal_code, seal_validation


@login_required
def seal_list(request):
    today = timezone.localdate()
    soon = today + timedelta(days=30)

    base_qs = Seal.objects.select_related("veiculo__proprietario")
    request_qs = SealRequest.objects.select_related("veiculo__proprietario")

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().upper()
    validade = (request.GET.get("validade") or "").strip().lower()

    qs = base_qs
    if q:
        qs = qs.filter(
            Q(numero_serial__icontains=q)
            | Q(veiculo__placa__icontains=q)
            | Q(veiculo__marca__icontains=q)
            | Q(veiculo__modelo__icontains=q)
            | Q(veiculo__proprietario__nome_preferido__icontains=q)
            | Q(veiculo__proprietario__first_name__icontains=q)
            | Q(veiculo__proprietario__last_name__icontains=q)
            | Q(veiculo__proprietario__cargo__icontains=q)
        )

    valid_statuses = {value for value, _label in Seal.Status.choices}
    if status in valid_statuses:
        qs = qs.filter(status=status)
    else:
        status = ""

    if validade == "sem_validade":
        qs = qs.filter(validade__isnull=True)
    elif validade == "vencendo":
        qs = qs.filter(status=Seal.Status.ATIVO, validade__gte=today, validade__lte=soon)
    elif validade == "vencido":
        qs = qs.filter(Q(status=Seal.Status.EXPIRADO) | Q(validade__lt=today))
    else:
        validade = ""

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Indicadores operacionais da base completa (não apenas do filtro atual).
    total_count = base_qs.count()
    active_count = base_qs.filter(status=Seal.Status.ATIVO).count()
    expiring_count = base_qs.filter(
        status=Seal.Status.ATIVO,
        validade__gte=today,
        validade__lte=soon,
    ).count()
    no_validity_count = base_qs.filter(validade__isnull=True).count()
    pending_request_count = request_qs.filter(status=SealRequest.Status.PENDENTE).count()

    requests = request_qs.order_by("-solicitado_em")[:20]

    context = {
        "seals": page_obj.object_list,
        "page_obj": page_obj,
        "requests": requests,
        "q": q,
        "status_filter": status,
        "validade_filter": validade,
        "total_count": total_count,
        "active_count": active_count,
        "expiring_count": expiring_count,
        "no_validity_count": no_validity_count,
        "pending_request_count": pending_request_count,
        "today": today,
        "soon": soon,
    }
    return render(request, "seals/list.html", context)


@login_required
def request_create(request):
    form = SealRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.usuario = obj.veiculo.proprietario
        if SealRequest.objects.filter(veiculo=obj.veiculo, status=SealRequest.Status.PENDENTE).exists():
            form.add_error("veiculo", "Já existe uma solicitação pendente para este veículo.")
        else:
            obj.save()
            messages.success(request, "Solicitação de selo registrada.")
            return redirect("seals:list")
    return render(request, "shared/form.html", {"form": form, "title": "Solicitar selo"})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def mobile_scanner(request):
    error = ""
    if request.method == "POST":
        try:
            lookup = parse_seal_code(request.POST.get("code"))
            seal = Seal.objects.get(**lookup)
        except ValueError as exc:
            error = str(exc)
        except Seal.DoesNotExist:
            error = "Selo não encontrado neste banco. Confira o número; este resultado não autoriza a entrada."
        except Seal.MultipleObjectsReturned:
            error = "Há mais de um número semelhante. Consulte pelo QR Code ou confira o cadastro."
        else:
            return redirect("seals:public", token=seal.token_publico)
    response = render(request, "seals/mobile_scanner.html", {"error": error}, status=400 if error else 200)
    response["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    response["Referrer-Policy"] = "same-origin"
    return response


@never_cache
@login_required
def public_query(request, token):
    seal = Seal.objects.select_related("veiculo__proprietario").filter(token_publico=token).first()
    if seal is None:
        return render(request, "seals/mobile_scanner.html", {"error": "Selo não encontrado neste banco. Leia outro QR ou confira o número."}, status=404)
    SealScan.objects.create(selo=seal, endereco_ip=request.META.get("REMOTE_ADDR"), agente_usuario=request.META.get("HTTP_USER_AGENT", "")[:250])
    response = render(request, "seals/public.html", {"seal": seal, "validation": seal_validation(seal)})
    response["Referrer-Policy"] = "same-origin"
    return response


@login_required
def qr_image(request, pk):
    seal = get_object_or_404(Seal.objects.select_related("veiculo__proprietario"), pk=pk)
    image = qrcode.make(seal.url_publica)
    output = BytesIO()
    image.save(output, format="PNG")
    return HttpResponse(output.getvalue(), content_type="image/png")


@login_required
def pdf_download(request, pk):
    seal = get_object_or_404(Seal.objects.select_related("veiculo__proprietario"), pk=pk)
    response = HttpResponse(generate_seal_pdf(seal), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="selo-{seal.numero_serial}.pdf"'
    return response
