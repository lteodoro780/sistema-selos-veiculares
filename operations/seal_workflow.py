import re
import secrets

from django import forms
from django.contrib import messages
from accounts.access import operator_required as staff_member_required
from django.db import IntegrityError, OperationalError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from people.models import Person
from seals.models import Seal
from vehicles.models import Vehicle


class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        identification = obj.cargo or obj.get_classe_funcional_display()
        section = obj.secao or "sem seção"
        return f"{obj.nome_exibicao} — {identification} — {section}"


class VehicleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        description = f"{obj.marca} {obj.modelo}".strip()
        return f"{obj.placa} — {obj.proprietario.nome_exibicao} — {description}"


class SealBaseForm(forms.Form):
    proprietario = PersonChoiceField(label="Proprietário", queryset=Person.objects.none())
    veiculo = VehicleChoiceField(label="Veículo", queryset=Vehicle.objects.none())
    validade = forms.DateField(
        label="Validade",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    ativar_apos_vinculo = forms.BooleanField(
        label="Ativar o selo agora",
        required=False,
        help_text="Exige proprietário ativo, veículo aprovado e validade de hoje ou futura.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proprietario"].queryset = Person.objects.all().order_by("-created_at", "nome_preferido", "first_name", "pk")
        self.fields["veiculo"].queryset = Vehicle.objects.select_related("proprietario").all().order_by("placa")

    def clean(self):
        data = super().clean()
        person = data.get("proprietario")
        vehicle = data.get("veiculo")
        if person and vehicle and vehicle.proprietario_id != person.pk:
            self.add_error("veiculo", "O veículo não pertence ao proprietário selecionado.")
        if data.get("ativar_apos_vinculo"):
            if person and not person.is_active:
                self.add_error("proprietario", "O cadastro do proprietário está inativo.")
            if vehicle and vehicle.status != Vehicle.Status.APROVADO:
                self.add_error("veiculo", "Aprove o veículo antes de ativar o selo.")
            if not data.get("validade") or data["validade"] < timezone.localdate():
                self.add_error("validade", "Informe uma validade de hoje ou futura para ativar.")
        return data


class ExistingSealForm(SealBaseForm):
    codigo_selo = forms.CharField(
        label="Código existente",
        max_length=24,
        help_text="Digite o código que já existe no selo físico. Ele não será transferido para outro veículo.",
    )

    def clean_codigo_selo(self):
        value = self.cleaned_data["codigo_selo"].strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9./-]{0,23}", value):
            raise forms.ValidationError("Use letras, números, ponto, barra ou hífen (até 24 caracteres).")
        return value


class GeneratedSealForm(SealBaseForm):
    pass


def _new_numeric_code():
    # Sempre oito dígitos e nunca começa por zero.
    return str(10_000_000 + secrets.randbelow(90_000_000))


def _current_locked_objects(data):
    person = Person.objects.select_for_update().get(pk=data["proprietario"].pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=data["veiculo"].pk)
    if vehicle.proprietario_id != person.pk:
        raise ValueError("O proprietário do veículo mudou. Reabra o formulário.")
    return person, vehicle


def _validate_activation(data, person, vehicle):
    activate = data["ativar_apos_vinculo"]
    if activate and (
        not person.is_active
        or vehicle.status != Vehicle.Status.APROVADO
        or not data["validade"]
        or data["validade"] < timezone.localdate()
    ):
        raise ValueError("Os dados mudaram ou não permitem ativação. Confira o veículo, proprietário e validade.")
    return activate


def _link_existing(form, request):
    with transaction.atomic():
        data = form.cleaned_data
        person, vehicle = _current_locked_objects(data)
        existing = list(Seal.objects.select_for_update().filter(numero_serial__iexact=data["codigo_selo"]))
        if len(existing) > 1:
            raise ValueError("Há códigos semelhantes no banco. Peça ao administrador para conferir os selos.")
        if existing:
            if existing[0].veiculo_id != vehicle.pk:
                raise ValueError("Este código já está vinculado a outro veículo. Nada foi alterado.")
            messages.info(request, "O selo já está vinculado a este veículo. Situação, validade e QR Code foram preservados.")
            return existing[0]
        if Seal.objects.filter(veiculo=vehicle).exists():
            raise ValueError("Este veículo já possui um selo. O vínculo existente foi preservado.")
        activate = _validate_activation(data, person, vehicle)
        seal = Seal.objects.create(
            numero_serial=data["codigo_selo"],
            veiculo=vehicle,
            validade=data["validade"],
            emitido_por=request.user,
            status=Seal.Status.ATIVO if activate else Seal.Status.PENDENTE,
        )
        messages.success(request, "Selo existente vinculado ao veículo. O QR Code está disponível na lista de selos.")
        return seal


def _create_generated(form, request):
    data = form.cleaned_data
    last_collision = None
    # O unique de numero_serial é a proteção final contra colisões concorrentes.
    for _ in range(25):
        code = _new_numeric_code()
        try:
            with transaction.atomic():
                person, vehicle = _current_locked_objects(data)
                if Seal.objects.select_for_update().filter(veiculo=vehicle).exists():
                    raise ValueError("Este veículo já possui um selo. O vínculo existente foi preservado.")
                activate = _validate_activation(data, person, vehicle)
                seal = Seal.objects.create(
                    numero_serial=code,
                    veiculo=vehicle,
                    validade=data["validade"],
                    emitido_por=request.user,
                    status=Seal.Status.ATIVO if activate else Seal.Status.PENDENTE,
                )
            messages.success(request, f"Novo selo criado. Código numérico: {code}.")
            return seal
        except IntegrityError as exc:
            # Se outra gravação usou o mesmo código no mesmo instante, tenta outro.
            if Seal.objects.filter(numero_serial=code).exists():
                last_collision = exc
                continue
            raise
    raise OperationalError("Não foi possível gerar um código numérico exclusivo após várias tentativas.") from last_collision


def _vehicle_owner_map():
    return {
        str(vehicle.pk): vehicle.proprietario_id
        for vehicle in Vehicle.objects.only("pk", "proprietario_id")
    }


@staff_member_required
def link_seal(request):
    mode = (request.POST.get("modo") or request.GET.get("modo") or "vincular").strip().lower()
    if mode not in {"vincular", "criar"}:
        mode = "vincular"

    existing_form = ExistingSealForm(prefix="existente")
    generated_form = GeneratedSealForm(prefix="novo")

    if request.method == "POST":
        if mode == "criar":
            generated_form = GeneratedSealForm(request.POST, prefix="novo")
            if generated_form.is_valid():
                try:
                    seal = _create_generated(generated_form, request)
                    return redirect(f"/operacoes/vincular-selo/?modo=criar&criado={seal.pk}")
                except (ValueError, IntegrityError, OperationalError) as exc:
                    message = str(exc) if isinstance(exc, ValueError) else "Conflito durante a criação. Nenhum selo foi substituído; confira os dados e tente novamente."
                    generated_form.add_error(None, message)
        else:
            existing_form = ExistingSealForm(request.POST, prefix="existente")
            if existing_form.is_valid():
                try:
                    _link_existing(existing_form, request)
                    return redirect("seals:list")
                except (ValueError, IntegrityError, OperationalError) as exc:
                    message = str(exc) if isinstance(exc, ValueError) else "Conflito durante o vínculo. Nenhum selo foi substituído; confira os dados e tente novamente."
                    existing_form.add_error(None, message)

    created_seal = None
    created_id = request.GET.get("criado", "").strip()
    if created_id:
        try:
            created_seal = Seal.objects.select_related("veiculo__proprietario").filter(pk=created_id).first()
        except (ValueError, TypeError):
            created_seal = None

    return render(
        request,
        "operations/link_seal.html",
        {
            "existing_form": existing_form,
            "generated_form": generated_form,
            "active_mode": mode,
            "created_seal": created_seal,
            "vehicle_owner_map": _vehicle_owner_map(),
        },
    )
