from django.conf import settings
from django.db import models

from vehicles.models import Vehicle


class StatusDocumento(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    VERIFICADO = "VERIFICADO", "Verificado"
    REJEITADO = "REJEITADO", "Rejeitado"
    VENCIDO = "VENCIDO", "Vencido"


class DriverDocument(models.Model):
    usuario = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="cnhs")
    numero = models.CharField("número da CNH", max_length=30)
    categoria = models.CharField(max_length=5)
    validade = models.DateField()
    arquivo = models.FileField(upload_to="documentos/cnh/%Y/%m/")
    status = models.CharField(max_length=20, choices=StatusDocumento.choices, default=StatusDocumento.PENDENTE)
    motivo_status = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "CNH"
        verbose_name_plural = "CNHs"

    def __str__(self):
        return f"CNH {self.numero} — {self.usuario.nome_exibicao}"


class VehicleDocument(models.Model):
    veiculo = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="crlvs")
    exercicio = models.PositiveSmallIntegerField("ano do licenciamento — exercício do CRLV")
    arquivo = models.FileField(upload_to="documentos/crlv/%Y/%m/")
    status = models.CharField(max_length=20, choices=StatusDocumento.choices, default=StatusDocumento.PENDENTE)
    motivo_status = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-exercicio", "-criado_em")
        verbose_name = "CRLV"
        verbose_name_plural = "CRLVs"
        constraints = [models.UniqueConstraint(fields=("veiculo", "exercicio"), name="unique_crlv_vehicle_year")]

    def __str__(self):
        return f"CRLV {self.veiculo.placa} / {self.exercicio}"
