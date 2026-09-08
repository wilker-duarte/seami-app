from django.urls import path
from . import views

app_name = 'papelaria'

urlpatterns = [
    path('', views.estoque_papelaria_view, name='estoque'),
    path('relatorio-pais/', views.relatorio_pais_view, name='relatorio_pais'),
    path('item/<int:item_id>/historico/', views.historico_item_json, name='historico_item_json'),
]
