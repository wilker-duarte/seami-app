from . import views
from django.urls import path
from .views import (
    lancar_chamada_view,
    salvar_chamada_lote_view,
    consulta_chamada_view,
    lista_alunos_view,
    lista_turmas_view,
    caderno_seami_view,
)

app_name = 'presencas'

urlpatterns = [
    path('chamada/', lancar_chamada_view, name='lancar_chamada'),
    path('chamada/salvar-lote/', salvar_chamada_lote_view, name='salvar_chamada_lote'),
    path('chamada/consulta/', consulta_chamada_view, name='consulta_chamada'),
    path('alunos/', lista_alunos_view, name='lista_alunos'),
    path('turmas/', lista_turmas_view, name='lista_turmas'),
    path('caderno-seami/', caderno_seami_view, name='caderno_seami_root'),
    path('caderno-seami/<str:aba>/', caderno_seami_view, name='caderno_seami'),
]
