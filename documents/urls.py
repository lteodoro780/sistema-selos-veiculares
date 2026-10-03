from django.urls import path
from . import views

app_name = "documents"
urlpatterns = [
    path('cnh/<int:pk>/editar/', views.document_edit, {'kind': 'cnh'}, name='cnh-edit'),
    path('crlv/<int:pk>/editar/', views.document_edit, {'kind': 'crlv'}, name='crlv-edit'),
    path("", views.document_list, name="list"),
    path("cnh/enviar/", views.cnh_create, name="cnh-create"),
    path("crlv/enviar/", views.crlv_create, name="crlv-create"),
]
