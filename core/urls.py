from django.urls import path
from .views import dashboard_view, relatorios_view

app_name = 'core'

urlpatterns = [
    path('', dashboard_view, name='dashboard'),
    path('relatorios/', relatorios_view, name='relatorios'),
]
