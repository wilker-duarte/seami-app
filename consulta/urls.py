from django.urls import path
from .views import consulta_publica_view

app_name = 'consulta'

urlpatterns = [
    path('', consulta_publica_view, name='painel'),
]
