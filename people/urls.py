from django.urls import path
from . import views

app_name = 'people'
urlpatterns = [
    path('', views.person_list, name='list'),
    path('incompletos/', views.person_list, {'incomplete': True}, name='incomplete'),
    path('adicionar/', views.person_edit, name='create'),
    path('pendencias/exportar/', views.export_pending, name='export'),
    path('pendencias/importar/', views.import_pending, name='import'),
    path('<int:pk>/', views.person_detail, name='detail'),
    path('<int:pk>/editar/', views.person_edit, name='edit'),
    path('<int:pk>/rapido/', views.quick_edit, name='quick'),
]
