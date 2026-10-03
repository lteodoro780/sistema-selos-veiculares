from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views


app_name = "accounts"
urlpatterns = [
    path("", views.dashboard, name="home"),
    path("entrar/", views.PortalLoginView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
    path("cadastro/", views.register, name="register"),
    path("painel/", views.dashboard, name="dashboard"),
    path("meu-cadastro/", views.profile, name="profile"),
    path("importar-csv/", views.csv_import, name="csv-import"),
    path("importar-csv/modelo/", views.csv_template, name="csv-template"),
]
