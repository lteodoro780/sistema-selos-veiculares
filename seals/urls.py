from django.urls import path
from . import views

app_name = "seals"
urlpatterns = [
    path("", views.seal_list, name="list"),
    path("celular/", views.mobile_scanner, name="mobile"),
    path("solicitar/", views.request_create, name="request-create"),
    path("consulta/<str:token>/", views.public_query, name="public"),
    path("<uuid:pk>/qr.png", views.qr_image, name="qr"),
    path("<uuid:pk>/pdf/", views.pdf_download, name="pdf"),
]
