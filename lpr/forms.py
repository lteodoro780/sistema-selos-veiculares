from django import forms

from .models import PlatePassage
from .plate_match import identify_format, normalize_plate


class PlatePassageCorrectionForm(forms.Form):
    plate = forms.CharField(
        label="Placa correta",
        max_length=12,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "class": "sv-manual-plate-input",
            "placeholder": "ABC1D23",
        }),
        help_text="Informe a placa correta. São aceitos os formatos antigo e Mercosul.",
    )
    movement = forms.ChoiceField(
        label="Movimento",
        choices=PlatePassage.Movement.choices,
    )
    learn_rule = forms.BooleanField(
        label="Usar esta correção nas próximas leituras iguais desta câmera",
        required=False,
        help_text="Ex.: se a câmera ler DEM1001 e você corrigir para DEM1C01, a próxima DEM1001 poderá ser corrigida automaticamente.",
    )
    note = forms.CharField(
        label="Observação",
        max_length=255,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Opcional: motivo ou conferência visual."}),
    )

    def clean_plate(self):
        plate = normalize_plate(self.cleaned_data["plate"])
        if len(plate) != 7 or identify_format(plate) == "DESCONHECIDA":
            raise forms.ValidationError("Informe uma placa brasileira válida: ABC1234 ou ABC1D23.")
        return plate
