from django.shortcuts import render
from core.views import build_dashboard_context, build_relatorios_context


def consulta_publica_view(request):
    """
    Portal de Consulta Externa SEAMI (Público, Read-Only, Sem Login).
    Apresenta exatamente:
    1. Dashboard da página inicial
    2. Relatórios do Caderno SEAMI (Relatórios Analíticos)
    """
    active_tab = request.GET.get('tab', 'dashboard').strip()
    if active_tab not in ['dashboard', 'relatorios']:
        active_tab = 'dashboard'

    if active_tab == 'relatorios':
        context = build_relatorios_context(request)
        context['is_public'] = True
        context['active_tab'] = 'relatorios'
        context['active_tab_nav'] = request.GET.get('subtab', request.GET.get('tab_relatorio', 'faltas'))
    else:
        context = build_dashboard_context(request)
        context['is_public'] = True
        context['active_tab'] = 'dashboard'

    return render(request, 'consulta/painel.html', context)
