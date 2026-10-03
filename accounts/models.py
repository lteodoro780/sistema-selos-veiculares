from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        USUARIO = "USUARIO", "Usuário"
        PATRULHANTE = "PATRULHANTE", "Patrulhante"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"

    class Vinculo(models.TextChoices):
        COLABORADOR = "COLABORADOR", "Colaborador"
        PRESTADOR = "PRESTADOR", "Prestador"
        OUTRO = "OUTRO", "Outro"

    class Classe(models.TextChoices):
        GRUPO_A = "GRUPO_A", "GRUPO A"
        GRUPO_B = "GRUPO_B", "GRUPO B"
        GRUPO_C = "GRUPO_C", "Grupo C"
        PRESTADOR = "PRESTADOR", "Prestador"
        SEM_CLASSE = "SEM_CLASSE", "Não informada"

    role = models.CharField("perfil", max_length=20, choices=Role.choices, default=Role.USUARIO)
    vinculo = models.CharField("vínculo", max_length=20, choices=Vinculo.choices, default=Vinculo.COLABORADOR)
    classe_funcional = models.CharField("classe funcional", max_length=20, choices=Classe.choices, default=Classe.SEM_CLASSE)
    cargo = models.CharField("cargo", max_length=60, blank=True)
    nome_preferido = models.CharField("nome preferido", max_length=80, blank=True)
    cpf = models.CharField("CPF", max_length=11, blank=True, unique=True, null=True)
    identidade_funcional = models.CharField("identidade funcional", max_length=30, blank=True)
    organizacao = models.CharField("organização", max_length=120, blank=True)
    secao = models.CharField("seção / setor", max_length=120, blank=True)
    telefone = models.CharField("telefone", max_length=30, blank=True)
    ramal = models.CharField("ramal", max_length=30, blank=True)
    cadastro_aprovado = models.BooleanField("cadastro aprovado", default=False)

    class Meta:
        verbose_name = "conta de acesso"
        verbose_name_plural = "contas de acesso"

    @property
    def nome_exibicao(self):
        return self.nome_preferido or self.get_full_name() or self.username

    @property
    def identificacao_funcional(self):
        return self.cargo or self.get_classe_funcional_display()

    def __str__(self):
        return f"{self.nome_exibicao} ({self.username})"
