from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'role':
            kwargs['choices'] = [(User.Role.ADMINISTRADOR, 'Administrador'), (User.Role.PATRULHANTE, 'Patrulhante')]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.is_staff = obj.role == User.Role.ADMINISTRADOR
        if obj.role == User.Role.PATRULHANTE:
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        if obj.role == User.Role.PATRULHANTE:
            obj.groups.clear()
            obj.user_permissions.clear()

    def get_queryset(self, request):
        from django.db.models import Q
        return super().get_queryset(request).filter(Q(is_superuser=True) | Q(role__in=["ADMINISTRADOR", "PATRULHANTE"]))

    list_display = ("username", "nome_exibicao", "role", "cargo", "secao", "cadastro_aprovado", "is_active")
    list_filter = ("role", "vinculo", "classe_funcional", "cadastro_aprovado", "is_active")
    search_fields = ("username", "first_name", "last_name", "nome_preferido", "cpf", "identidade_funcional", "secao", "telefone", "ramal")
    fieldsets = UserAdmin.fieldsets + (("Dados funcionais", {"fields": (
        "role", "vinculo", "classe_funcional", "cargo", "nome_preferido", "cpf",
        "identidade_funcional", "organizacao", "secao", "telefone", "ramal", "cadastro_aprovado",
    )}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Dados funcionais", {"fields": ("role", "cadastro_aprovado")}),)
