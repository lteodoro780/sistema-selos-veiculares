from django import forms
from vehicles.models import Vehicle
from .models import SealRequest


class SealRequestForm(forms.ModelForm):
    class Meta:
        model = SealRequest
        fields = ("veiculo", "observacao_usuario")

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            self.fields["veiculo"].queryset = Vehicle.objects.filter(proprietario=usuario, status=Vehicle.Status.APROVADO).exclude(selo__isnull=False)
