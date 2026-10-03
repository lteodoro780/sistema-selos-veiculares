from django.contrib import admin
from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("placa", "marca", "modelo", "proprietario", "status", "atualizado_em")
    list_filter = ("status", "tipo", "marca")
    search_fields = ("placa", "renavam", "chassi", "proprietario__username", "proprietario__nome_preferido")
    autocomplete_fields = ("proprietario",)
