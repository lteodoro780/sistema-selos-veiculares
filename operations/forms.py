from django import forms
from .models import Occurrence
from people.models import Person
from vehicles.models import Vehicle
from django.utils import timezone
import re


class OccurrenceForm(forms.ModelForm):
    class Meta:
        model = Occurrence
        fields = ("proprietario", "veiculo", "selo", "tipo", "status", "data_hora", "local", "descricao", "providencias")
        widgets = {"data_hora": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_hora"].input_formats = ("%Y-%m-%dT%H:%M",)

    def clean(self):
        cleaned = super().clean()
        vehicle = cleaned.get("veiculo")
        owner = cleaned.get("proprietario")
        seal = cleaned.get("selo")
        if vehicle and owner and vehicle.proprietario_id != owner.id:
            self.add_error("veiculo", "O veículo não pertence ao proprietário selecionado.")
        if seal and vehicle and seal.veiculo_id != vehicle.id:
            self.add_error("selo", "O selo não pertence ao veículo selecionado.")
        return cleaned


class VehicleOwnerChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.placa} — {obj.proprietario} — {obj.marca} {obj.modelo}'


class SealLinkForm(forms.Form):
    codigo_selo = forms.CharField(label='Código do selo', max_length=24,
                                 help_text='Informe o código já impresso. Um código vinculado não pode ser transferido por esta tela.')
    proprietario = forms.ModelChoiceField(label='Proprietário', queryset=Person.objects.all())
    veiculo = VehicleOwnerChoice(label='Veículo', queryset=Vehicle.objects.select_related('proprietario').all())
    validade = forms.DateField(label='Validade', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ativar_apos_vinculo = forms.BooleanField(label='Ativar o novo selo', required=False,
                                           help_text='Exige proprietário ativo, veículo aprovado e validade futura ou de hoje.')

    def clean_codigo_selo(self):
        value = self.cleaned_data['codigo_selo'].strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9./-]{0,23}', value):
            raise forms.ValidationError('Use letras, números, ponto, barra ou hífen (até 24 caracteres).')
        return value

    def clean(self):
        data = super().clean()
        person, vehicle = data.get('proprietario'), data.get('veiculo')
        if person and vehicle and vehicle.proprietario_id != person.pk:
            self.add_error('veiculo', 'O veículo não pertence ao proprietário selecionado.')
        if data.get('ativar_apos_vinculo'):
            if person and not person.is_active:
                self.add_error('proprietario', 'O cadastro do proprietário está inativo.')
            if vehicle and vehicle.status != Vehicle.Status.APROVADO:
                self.add_error('veiculo', 'Aprove o veículo antes de ativar o selo.')
            if not data.get('validade') or data['validade'] < timezone.localdate():
                self.add_error('validade', 'Informe uma validade de hoje ou futura para ativar.')
        return data
