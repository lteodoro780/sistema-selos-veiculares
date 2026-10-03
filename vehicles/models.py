from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class Status(models.TextChoices):
        EM_ANALISE = "EM_ANALISE", "Em análise"
        APROVADO = "APROVADO", "Aprovado"
        REJEITADO = "REJEITADO", "Rejeitado"
        INATIVO = "INATIVO", "Inativo"

    class Tipo(models.TextChoices):
        CARRO = "CARRO", "Carro"
        MOTO = "MOTO", "Motocicleta"
        CAMINHONETE = "CAMINHONETE", "Caminhonete"
        OUTRO = "OUTRO", "Outro"

    proprietario = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="veiculos")
    placa = models.CharField(max_length=7, unique=True)
    renavam = models.CharField(max_length=11, unique=True)
    chassi = models.CharField(max_length=17, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.CARRO)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=80)
    cor = models.CharField(max_length=40)
    ano_fabricacao = models.PositiveSmallIntegerField("ano de fabricação")
    ano_modelo = models.PositiveSmallIntegerField("ano do modelo")
    foto_dianteira = models.ImageField(upload_to="veiculos/%Y/%m/", blank=True)
    foto_traseira = models.ImageField(upload_to="veiculos/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EM_ANALISE)
    motivo_status = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("placa",)
        verbose_name = "veículo"
        verbose_name_plural = "veículos"

    def save(self, *args, **kwargs):
        self.placa = "".join(ch for ch in self.placa.upper() if ch.isalnum())
        self.renavam = "".join(ch for ch in self.renavam if ch.isdigit()).zfill(11)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.placa} — {self.marca} {self.modelo}"
