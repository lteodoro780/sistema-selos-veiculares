from django.urls import path
from . import views

app_name = "vehicles"
urlpatterns = [
    path("", views.vehicle_list, name="list"),
    path("pessoas/buscar/", views.vehicle_person_search, name="person-search"),
    path("adicionar/", views.vehicle_create, name="create"),
    path("<int:pk>/editar/", views.vehicle_edit, name="edit"),
]
