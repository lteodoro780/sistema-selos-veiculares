from pathlib import Path

from django import forms

from .models import DriverDocument, VehicleDocument


MAX_SIZE = 15 * 1024 * 1024
ALLOWED = {".pdf", ".jpg", ".jpeg", ".png"}


def validate_file(upload):
    if upload.size > MAX_SIZE:
        raise forms.ValidationError("O arquivo não pode ultrapassar 15 MB.")
    if Path(upload.name).suffix.lower() not in ALLOWED:
        raise forms.ValidationError("Use PDF, JPG ou PNG.")
    return upload


class DriverDocumentForm(forms.ModelForm):
    class Meta:
        model = DriverDocument
        fields = ("usuario", "numero", "categoria", "validade", "arquivo", "status", "motivo_status")
        widgets = {"validade": forms.DateInput(attrs={"type": "date"})}

    def clean_arquivo(self):
        return validate_file(self.cleaned_data["arquivo"])


class VehicleDocumentForm(forms.ModelForm):
    class Meta:
        model = VehicleDocument
        fields = ("veiculo", "exercicio", "arquivo", "status", "motivo_status")

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["veiculo"].queryset = usuario.veiculos.all()

    def clean_arquivo(self):
        return validate_file(self.cleaned_data["arquivo"])
