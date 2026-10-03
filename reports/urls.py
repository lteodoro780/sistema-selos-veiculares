from django.urls import path
from . import views

app_name = 'reports'
urlpatterns = [path('', views.report, name='index'), path('exportar.csv', views.export_csv, name='csv')]
