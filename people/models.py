import uuid

from django.conf import settings
from django.db import models

from accounts.models import User


class Person(models.Model):
    Vinculo = User.Vinculo
    Classe = User.Classe

    class Review(models.TextChoices):
        PENDING = 'PENDING', 'Aguardando conferência'
        VERIFIED = 'VERIFIED', 'Conferido'

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    legacy_user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='person_record', editable=False)
    username = models.CharField('referência da importação', max_length=150, unique=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField('nome', max_length=150, blank=True)
    last_name = models.CharField('sobrenome', max_length=150, blank=True)
    nome_preferido = models.CharField('nome preferido', max_length=80, blank=True)
    email = models.EmailField('e-mail', blank=True)
    cpf = models.CharField('CPF', max_length=11, null=True, blank=True, unique=True)
    vinculo = models.CharField('vínculo', max_length=20, choices=Vinculo.choices, default=Vinculo.COLABORADOR)
    classe_funcional = models.CharField('categoria', max_length=20, choices=Classe.choices, default=Classe.SEM_CLASSE)
    cargo = models.CharField('cargo', max_length=60, blank=True)
    identidade_funcional = models.CharField('identidade funcional', max_length=30, blank=True)
    organizacao = models.CharField('organização', max_length=120, blank=True)
    secao = models.CharField('seção / setor', max_length=120, blank=True)
    telefone = models.CharField('telefone', max_length=30, blank=True)
    ramal = models.CharField('ramal', max_length=30, blank=True)
    is_active = models.BooleanField('cadastro ativo', default=True)
    cadastro_aprovado = models.BooleanField(default=False)
    review_status = models.CharField('conferência', max_length=12, choices=Review.choices, default=Review.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('nome_preferido', 'first_name', 'pk')
        verbose_name = 'pessoa'
        verbose_name_plural = 'pessoas'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def nome_exibicao(self):
        return self.nome_preferido or self.get_full_name() or f'Pessoa #{self.pk}'

    @property
    def identificacao_funcional(self):
        return self.cargo or self.get_classe_funcional_display()

    @property
    def missing_fields(self):
        missing = []
        if not self.first_name.strip():
            missing.append(('nome', 'Nome'))
        if self.vinculo == self.Vinculo.COLABORADOR and not self.cargo.strip():
            missing.append(('graduacao', 'Cargo'))
        if not self.secao.strip():
            missing.append(('secao', 'Seção / setor'))
        if not self.telefone.strip() and not self.ramal.strip():
            missing.append(('contato', 'Telefone ou ramal'))
        if not self.identidade_funcional.strip() and not self.cpf:
            missing.append(('identificacao', 'Identidade funcional ou CPF'))
        return missing

    @property
    def completion_status(self):
        if self.missing_fields:
            return 'Incompleto'
        return self.get_review_status_display()

    def __str__(self):
        return f'{self.cargo} {self.nome_exibicao}'.strip()


class PersonChange(models.Model):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='changes')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    at = models.DateTimeField(auto_now_add=True)
    source = models.CharField('origem', max_length=200)
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ('-at', '-pk')
        verbose_name = 'alteração de cadastro'
        verbose_name_plural = 'histórico dos cadastros'


class CompletionImport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    filename = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=list)
    replace_existing = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)
