from django.contrib import admin
from .models import Occurrence


@admin.register(Occurrence)
class OccurrenceAdmin(admin.ModelAdmin):
    list_display = ("numero", "data_hora", "tipo", "status", "veiculo", "proprietario", "registrado_por")
    list_filter = ("tipo", "status", "data_hora")
    search_fields = ("numero", "veiculo__placa", "proprietario__username", "proprietario__nome_preferido", "local", "descricao")
    autocomplete_fields = ("proprietario", "veiculo", "selo", "registrado_por")
    readonly_fields = ("numero", "criado_em", "atualizado_em")
