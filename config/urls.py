from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import logout_view
from presencas.views import lista_alunos_view, lista_turmas_view, caderno_seami_view
from core.views import relatorios_view, central_exportacao_view

urlpatterns = [
    # Intercepta qualquer logout (inclusive do Django Admin) para direcionar para o login do SEAMI
    path('admin/logout/', logout_view, name='admin_logout'),
    path('logout/', logout_view, name='root_logout'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('alunos/', lista_alunos_view, name='alunos'),
    path('turmas/', lista_turmas_view, name='turmas'),
    path('exportacao/', central_exportacao_view, name='exportacao'),
    path('relatorios/', relatorios_view, name='relatorios'),
    path('caderno-seami/', caderno_seami_view, name='caderno_seami_root'),
    path('caderno-seami/<str:aba>/', caderno_seami_view, name='caderno_seami'),
    path('', include('core.urls', namespace='core')),
    path('presencas/', include('presencas.urls', namespace='presencas')),
    
    # Portal Público de Consulta Externa (Read-Only, Sem Login)
    path('consulta/', include('consulta.urls', namespace='consulta')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
