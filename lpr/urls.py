from django.urls import path

from . import views

app_name = "lpr"

urlpatterns = [
    path("", views.passage_list, name="list"),
    path("<int:pk>/editar/", views.passage_edit, name="edit"),
    path("<int:pk>/imagem/", views.passage_image, name="image"),
]
