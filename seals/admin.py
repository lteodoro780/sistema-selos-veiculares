from django.contrib import admin, messages
from django.utils import timezone

from .models import Seal, SealRequest, SealScan


@admin.register(Seal)
class SealAdmin(admin.ModelAdmin):
    list_display = ("numero_serial", "veiculo", "status", "validade", "emitido_em")
    list_filter = ("status", "validade")
    search_fields = ("numero_serial", "veiculo__placa", "veiculo__proprietario__username")
    autocomplete_fields = ("veiculo", "emitido_por")
    readonly_fields = ("numero_serial", "token_publico", "emitido_em", "atualizado_em")

    def save_model(self, request, obj, form, change):
        if not obj.emitido_por:
            obj.emitido_por = request.user
        super().save_model(request, obj, form, change)


@admin.action(description="Aprovar e emitir selo pendente")
def approve_requests(modeladmin, request, queryset):
    total = 0
    for item in queryset.filter(status=SealRequest.Status.PENDENTE):
        Seal.objects.get_or_create(veiculo=item.veiculo, defaults={"emitido_por": request.user})
        item.status = SealRequest.Status.APROVADA
        item.analisado_por = request.user
        item.analisado_em = timezone.now()
        item.save(update_fields=("status", "analisado_por", "analisado_em"))
        total += 1
    messages.success(request, f"{total} solicitação(ões) aprovada(s).")


@admin.register(SealRequest)
class SealRequestAdmin(admin.ModelAdmin):
    list_display = ("veiculo", "usuario", "status", "solicitado_em", "analisado_por")
    list_filter = ("status", "solicitado_em")
    search_fields = ("veiculo__placa", "usuario__username", "usuario__nome_preferido")
    actions = (approve_requests,)


@admin.register(SealScan)
class SealScanAdmin(admin.ModelAdmin):
    list_display = ("selo", "consultado_em", "endereco_ip")
    readonly_fields = ("selo", "consultado_em", "endereco_ip", "agente_usuario")
