from django.urls import path
from .views import dashboard_view, relatorios_view, central_exportacao_view
from .enfermaria_views import (
    enfermaria_dashboard_view,
    enfermaria_novo_atendimento_view,
    enfermaria_editar_atendimento_view,
    enfermaria_deletar_atendimento_view,
    enfermaria_aluno_info_api
)
from .admin_views import (
    central_administrativa_view,
    salvar_orgao_api,
    toggle_orgao_status_api,
    excluir_orgao_api
)

app_name = 'core'

urlpatterns = [
    path('', dashboard_view, name='dashboard'),
    path('relatorios/', relatorios_view, name='relatorios'),
    path('exportacao/', central_exportacao_view, name='exportacao'),
    
    # Central Administrativa
    path('administracao/', central_administrativa_view, name='central_administrativa'),
    path('administracao/orgaos/salvar/', salvar_orgao_api, name='salvar_orgao_api'),
    path('administracao/orgaos/<int:orgao_id>/toggle/', toggle_orgao_status_api, name='toggle_orgao_status_api'),
    path('administracao/orgaos/<int:orgao_id>/excluir/', excluir_orgao_api, name='excluir_orgao_api'),

    # Módulo III: Enfermagem
    path('enfermaria/', enfermaria_dashboard_view, name='enfermaria'),
    path('enfermaria/novo/', enfermaria_novo_atendimento_view, name='enfermaria_novo'),
    path('enfermaria/<int:atendimento_id>/editar/', enfermaria_editar_atendimento_view, name='enfermaria_editar'),
    path('enfermaria/<int:atendimento_id>/deletar/', enfermaria_deletar_atendimento_view, name='enfermaria_deletar'),
    path('enfermaria/aluno/<int:aluno_id>/info/', enfermaria_aluno_info_api, name='enfermaria_aluno_info'),
]

