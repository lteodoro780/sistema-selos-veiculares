from django.urls import path
from . import views
from . import seal_workflow

app_name = "operations"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path('vincular-selo/', seal_workflow.link_seal, name='link-seal'),
    path("usuarios/<int:pk>/", views.user_detail, name="user-detail"),
    path("ocorrencias/", views.occurrence_list, name="occurrence-list"),
    path("ocorrencias/pessoas/buscar/", views.occurrence_people_search, name="occurrence-person-search"),
    path("ocorrencias/adicionar/", views.occurrence_create, name="occurrence-create"),
    path("ocorrencias/<int:pk>/editar/", views.occurrence_edit, name="occurrence-edit"),
    path("ocorrencias/exportar.csv", views.occurrence_csv, name="occurrence-csv"),
]
