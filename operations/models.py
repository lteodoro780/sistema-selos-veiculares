import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from seals.models import Seal
from vehicles.models import Vehicle


def generate_number():
    return f"OC-{timezone.localdate().year}-{secrets.token_hex(4).upper()}"


class Occurrence(models.Model):
    class Tipo(models.TextChoices):
        ABORDAGEM = "ABORDAGEM", "Abordagem"
        IRREGULARIDADE = "IRREGULARIDADE", "Irregularidade"
        ACIDENTE = "ACIDENTE", "Acidente"
        FURTO_DUMBO = "FURTO_DUMBO", "Furto / roubo"
        SELO_DANIFICADO = "SELO_DANIFICADO", "Selo danificado"
        SELO_IRREGULAR = "SELO_IRREGULAR", "Selo irregular"
        DOCUMENTO = "DOCUMENTO", "Problema documental"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        EM_ANALISE = "EM_ANALISE", "Em análise"
        ENCERRADA = "ENCERRADA", "Encerrada"

    numero = models.CharField(max_length=24, unique=True, default=generate_number, editable=False)
    proprietario = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="ocorrencias")
    veiculo = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="ocorrencias")
    selo = models.ForeignKey(Seal, on_delete=models.SET_NULL, null=True, blank=True, related_name="ocorrencias")
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABERTA)
    data_hora = models.DateTimeField("data e hora", default=timezone.now)
    local = models.CharField(max_length=200)
    descricao = models.TextField("descrição")
    providencias = models.TextField("providências", blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ocorrencias_registradas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-data_hora",)
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"

    def __str__(self):
        return f"{self.numero} — {self.veiculo.placa}"
