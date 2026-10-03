from django.contrib import admin
from .models import Person, PersonChange


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome_exibicao', 'cargo', 'secao', 'telefone', 'ramal', 'completion_status')
    search_fields = ('first_name', 'last_name', 'nome_preferido', 'secao', 'cpf', 'telefone')
    list_filter = ('vinculo', 'classe_funcional', 'is_active', 'review_status')
    readonly_fields = ('public_id', 'username', 'legacy_user', 'reviewed_by', 'reviewed_at', 'updated_at', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PersonChange)
class PersonChangeAdmin(admin.ModelAdmin):
    list_display = ('person', 'actor', 'at', 'source')
    readonly_fields = ('person', 'actor', 'at', 'source', 'changes')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
