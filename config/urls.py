from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import logout_view
from presencas.views import lista_alunos_view, lista_turmas_view, caderno_seami_view
from core.views import relatorios_view, central_exportacao_view
from core.enfermaria_views import enfermaria_dashboard_view

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
    path('enfermaria/', enfermaria_dashboard_view, name='enfermaria'),
    path('caderno-seami/', caderno_seami_view, name='caderno_seami_root'),
    path('caderno-seami/<str:aba>/', caderno_seami_view, name='caderno_seami'),
    path('', include('core.urls', namespace='core')),
    path('presencas/', include('presencas.urls', namespace='presencas')),
    
    # Portal Público de Consulta Externa (Read-Only, Sem Login)
    path('consulta/', include('consulta.urls', namespace='consulta')),
]


from urllib.parse import unquote
import os
import re
import unicodedata
from django.urls import re_path
from django.http import Http404
from django.views.static import serve


def normalize_media_filename(text):
    """Normaliza nomes de arquivos para busca tolerante e flexível."""
    if not text:
        return ""
    text = unquote(str(text))
    # Remove prefixo numérico de timestamp (ex: 1786633542762_)
    clean = re.sub(r'^\d{10,14}_', '', text.strip())
    # Remove sufixos aleatórios do Django (ex: _xkSWukX.pdf -> .pdf)
    clean = re.sub(r'_[a-zA-Z0-9]{7}(\.[a-zA-Z0-9]+)$', r'\1', clean)
    # Remove acentuação
    nfkd = unicodedata.normalize('NFKD', clean)
    clean = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Substitui underlines por espaços e passa para minúsculas
    clean = clean.replace('_', ' ').replace('-', ' ').lower()
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def smart_serve_media(request, path, document_root=None):
    """
    Serviço Inteligente de Mídia:
    1. Tenta servir o caminho exato.
    2. Se não encontrar, busca no diretório ignorando timestamps legados (178..._),
       sufixos aleatórios do Django (_xkSWukX), variações de espaço/underline e acentos.
    """
    if not document_root:
        document_root = settings.MEDIA_ROOT

    # 1. Caminho Exato
    clean_path = unquote(path)
    full_path = os.path.abspath(os.path.join(str(document_root), clean_path))
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return serve(request, clean_path, document_root=document_root)

    # 2. Busca Inteligente no Diretório
    dir_name = os.path.dirname(full_path)
    file_name = os.path.basename(clean_path)

    if os.path.exists(dir_name) and os.path.isdir(dir_name):
        norm_target = normalize_media_filename(file_name)
        target_base, target_ext = os.path.splitext(file_name)
        norm_target_base = normalize_media_filename(target_base)

        best_match = None
        arquivos_disco = [f for f in os.listdir(dir_name) if os.path.isfile(os.path.join(dir_name, f))]

        # Tentativa A: Match exato removendo apenas o timestamp numérico inicial (178..._)
        for f in arquivos_disco:
            f_clean = re.sub(r'^\d{10,14}_', '', f)
            if f_clean.lower() == file_name.lower() or f_clean.replace(' ', '_').lower() == file_name.lower() or f_clean.replace('_', ' ').lower() == file_name.lower():
                best_match = f
                break

        # Tentativa B: Match normalizado completo
        if not best_match:
            for f in arquivos_disco:
                f_norm = normalize_media_filename(f)
                if f_norm == norm_target:
                    best_match = f
                    break

        # Tentativa C: Match de nome base sem sufixos aleatórios (_xkSWukX)
        if not best_match:
            for f in arquivos_disco:
                f_base, f_ext = os.path.splitext(f)
                if normalize_media_filename(f_base) == norm_target_base:
                    best_match = f
                    break

        # Tentativa D: Correspondência parcial / substring com mesma extensão
        if not best_match and norm_target_base and len(norm_target_base) > 4:
            for f in arquivos_disco:
                f_base, f_ext = os.path.splitext(f)
                f_norm_base = normalize_media_filename(f_base)
                if (norm_target_base in f_norm_base or f_norm_base in norm_target_base) and (not target_ext or target_ext.lower() == f_ext.lower()):
                    best_match = f
                    break

        if best_match:
            # Encontrou o arquivo físico correspondente
            rel_dir = os.path.relpath(dir_name, str(document_root))
            rel_path = os.path.join(rel_dir, best_match).replace('\\', '/')
            if rel_path.startswith('./'):
                rel_path = rel_path[2:]
            return serve(request, rel_path, document_root=document_root)

    # 3. Não encontrado
    raise Http404(f'Arquivo de mídia "{path}" não foi encontrado no servidor.')


urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', smart_serve_media, {'document_root': settings.MEDIA_ROOT}),
]
