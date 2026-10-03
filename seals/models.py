import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from vehicles.models import Vehicle


def generate_serial():
    return f"SV-{timezone.localdate().year}-{secrets.token_hex(4).upper()}"


def generate_public_token():
    return secrets.token_urlsafe(32)


class Seal(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ATIVO = "ATIVO", "Ativo"
        BLOQUEADO = "BLOQUEADO", "Bloqueado"
        CANCELADO = "CANCELADO", "Cancelado"
        EXPIRADO = "EXPIRADO", "Expirado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_serial = models.CharField(max_length=24, unique=True, default=generate_serial, editable=False)
    token_publico = models.CharField(max_length=64, unique=True, default=generate_public_token, editable=False)
    veiculo = models.OneToOneField(Vehicle, on_delete=models.PROTECT, related_name="selo")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    validade = models.DateField(null=True, blank=True)
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="selos_emitidos")
    emitido_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-emitido_em",)
        verbose_name = "selo"
        verbose_name_plural = "selos"

    @property
    def url_publica(self):
        return f"{settings.PUBLIC_BASE_URL}/selos/consulta/{self.token_publico}/"

    def __str__(self):
        return f"{self.numero_serial} — {self.veiculo.placa}"


class SealRequest(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        APROVADA = "APROVADA", "Aprovada"
        REJEITADA = "REJEITADA", "Rejeitada"

    usuario = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="solicitacoes_selo")
    veiculo = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="solicitacoes_selo")
    observacao_usuario = models.TextField("observação", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    solicitado_em = models.DateTimeField(auto_now_add=True)
    analisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitacoes_analisadas")
    analisado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-solicitado_em",)
        verbose_name = "solicitação de selo"
        verbose_name_plural = "solicitações de selo"

    def __str__(self):
        return f"{self.veiculo.placa} — {self.get_status_display()}"


class SealScan(models.Model):
    selo = models.ForeignKey(Seal, on_delete=models.CASCADE, related_name="consultas")
    consultado_em = models.DateTimeField(auto_now_add=True)
    endereco_ip = models.GenericIPAddressField(null=True, blank=True)
    agente_usuario = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ("-consultado_em",)
        verbose_name = "consulta de selo"
        verbose_name_plural = "consultas de selos"
