from django.contrib import admin
from .models import DriverDocument, VehicleDocument


@admin.register(DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ("numero", "usuario", "categoria", "validade", "status", "criado_em")
    list_filter = ("status", "categoria", "validade")
    search_fields = ("numero", "usuario__username", "usuario__nome_preferido")
    autocomplete_fields = ("usuario",)


@admin.register(VehicleDocument)
class VehicleDocumentAdmin(admin.ModelAdmin):
    list_display = ("veiculo", "exercicio", "status", "criado_em")
    list_filter = ("status", "exercicio")
    search_fields = ("veiculo__placa", "veiculo__proprietario__username")
    autocomplete_fields = ("veiculo",)
