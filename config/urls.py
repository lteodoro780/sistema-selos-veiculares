from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from .private_media import download


urlpatterns = [
    path('media/<path:name>', download, name='private-media'),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("pessoas/", include("people.urls")),
    path("veiculos/", include("vehicles.urls")),
    path("documentos/", include("documents.urls")),
    path("selos/", include("seals.urls")),
    path("operacoes/", include("operations.urls")),
    path("placas/", include("lpr.urls")),
    path('relatorios/', include('reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Sistema de Selos Veiculares"
admin.site.site_title = "Administração de Selos"
admin.site.index_title = "Administração"
