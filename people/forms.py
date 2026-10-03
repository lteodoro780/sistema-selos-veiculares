import re

from django import forms
from .models import Person


EDIT_FIELDS = ('first_name', 'last_name', 'nome_preferido', 'vinculo', 'classe_funcional',
               'cargo', 'identidade_funcional', 'cpf', 'organizacao',
               'secao', 'telefone', 'ramal', 'email')


def normalize_contact(value, extension=False):
    raw = str(value or '').strip()
    if not raw:
        return ''
    if not re.fullmatch(r'[\d\s()+.\-]+', raw):
        raise forms.ValidationError('Informe apenas um número por campo, sem letras.')
    digits = re.sub(r'\D', '', raw)
    if extension:
        if not 1 <= len(digits) <= 13:
            raise forms.ValidationError('Informe um ramal ou número de contato válido.')
        return digits
    if len(digits) not in {8, 9, 10, 11, 12, 13} or (len(digits) > 11 and not digits.startswith('55')):
        raise forms.ValidationError('Informe um telefone com 8 a 11 dígitos ou +55. Números curtos devem ficar em Ramal.')
    from accounts.csv_import import _format_phone_digits
    return _format_phone_digits(digits)


class PersonForm(forms.ModelForm):
    cpf = forms.CharField(label='CPF', required=False, max_length=14)
    source = forms.ChoiceField(label='Origem da informação', choices=(
        ('Edição administrativa', 'Edição administrativa'), ('Documento', 'Documento'),
        ('Contato telefônico', 'Contato telefônico'), ('Cadastro anterior', 'Cadastro anterior')))
    review_status = forms.ChoiceField(label='Conferência', choices=Person.Review.choices)
    version = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Person
        fields = (*EDIT_FIELDS, 'is_active', 'review_status')
        labels = {'first_name': 'Nome completo (ou nome + sobrenome abaixo)'}

    def clean_telefone(self):
        if self.instance.pk and self.cleaned_data.get('telefone') == self.instance.telefone:
            return self.instance.telefone
        return normalize_contact(self.cleaned_data.get('telefone'))

    def clean_ramal(self):
        if self.instance.pk and self.cleaned_data.get('ramal') == self.instance.ramal:
            return self.instance.ramal
        return normalize_contact(self.cleaned_data.get('ramal'), extension=True)

    def clean_cpf(self):
        raw = self.cleaned_data.get('cpf') or ''
        digits = re.sub(r'\D', '', raw)
        if digits and len(digits) != 11:
            raise forms.ValidationError('O CPF deve ter 11 dígitos.')
        return digits or None

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('review_status') == Person.Review.VERIFIED:
            candidate = Person(**{field: cleaned.get(field, getattr(self.instance, field)) for field in EDIT_FIELDS})
            if candidate.missing_fields:
                self.add_error('review_status', 'Preencha as pendências antes de marcar como conferido.')
        return cleaned


class CompletionUploadForm(forms.Form):
    arquivo = forms.FileField(label='Planilha de pendências preenchida', widget=forms.ClearableFileInput(attrs={'accept': '.xlsx,.csv'}))
    replace_existing = forms.BooleanField(required=False, label='Permitir substituir dados já preenchidos (serão mostrados na prévia)')

    def clean_arquivo(self):
        upload = self.cleaned_data['arquivo']
        if not upload.name.lower().endswith(('.xlsx', '.csv')) or upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Selecione XLSX ou CSV de até 5 MB.')
        return upload
