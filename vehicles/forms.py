import re
from datetime import date

from django import forms

from .models import Vehicle


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ("proprietario", "placa", "renavam", "chassi", "tipo", "marca", "modelo", "cor", "ano_fabricacao", "ano_modelo", "foto_dianteira", "foto_traseira", "status", "motivo_status")

    def clean_placa(self):
        value = re.sub(r"[^A-Za-z0-9]", "", self.cleaned_data["placa"]).upper()
        if len(value) != 7:
            raise forms.ValidationError("A placa deve ter 7 caracteres.")
        return value

    def clean_renavam(self):
        value = re.sub(r"\D", "", self.cleaned_data["renavam"])
        if len(value) not in (9, 10, 11):
            raise forms.ValidationError("Informe um Renavam com 9, 10 ou 11 números.")
        return value.zfill(11)

    def clean(self):
        cleaned = super().clean()
        current = date.today().year + 1
        for field in ("ano_fabricacao", "ano_modelo"):
            if cleaned.get(field) and not 1900 <= cleaned[field] <= current:
                self.add_error(field, f"Informe um ano entre 1900 e {current}.")
        return cleaned
