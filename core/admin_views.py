import json
from datetime import datetime, date
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Q

from accounts.permissions import diretor_required
from accounts.models import User, UserRole
from presencas.models import (
    Orgao, Aluno, Turma, DiaNaoLetivo, TipoDiaNaoLetivo, RegistroPresenca, DiarioDeClasse, OcorrenciaCaderno
)


@login_required
@diretor_required
def central_administrativa_view(request):
    """
    Central Administrativa do SEAMI:
    Área de gestão integrada e amigável (fora do Django Admin) para
    órgãos conveniados, calendário escolar (feriados/recessos), turmas e parâmetros.
    """
    today = timezone.localdate()
    current_year = today.year

    active_tab = request.GET.get('tab', 'geral').strip().lower()
    if active_tab not in ['geral', 'orgaos', 'feriados', 'turmas', 'usuarios']:
        active_tab = 'geral'

    # =========================================================================
    # 1. INDICADORES GERAIS DE GESTÃO DO SISTEMA
    # =========================================================================
    total_alunos_ativos = Aluno.objects.ativos().count()
    total_alunos_cadastrados = Aluno.objects.count()
    total_alunos_conveniados = Aluno.objects.ativos().filter(orgao__isnull=False).count()
    total_alunos_sem_orgao = total_alunos_ativos - total_alunos_conveniados

    total_turmas = Turma.objects.filter(ativo=True).count()
    total_orgaos = Orgao.objects.count()
    total_orgaos_ativos = Orgao.objects.filter(ativo=True).count()
    total_usuarios_ativos = User.objects.filter(is_active=True).count()
    total_feriados_ano = DiaNaoLetivo.objects.filter(data_inicio__year=current_year).count()

    usuarios_por_role = {
        'master': User.objects.filter(is_active=True, role=UserRole.MASTER_ADMIN).count(),
        'diretor': User.objects.filter(is_active=True, role=UserRole.DIRETOR).count(),
        'professor': User.objects.filter(is_active=True, role=UserRole.PROFESSOR).count(),
        'auxiliar': User.objects.filter(is_active=True, role=UserRole.AUXILIAR).count(),
        'enfermeira': User.objects.filter(is_active=True, role=UserRole.ENFERMEIRA).count(),
    }

    # =========================================================================
    # 2. LISTAGEM COMPLETA E DETALHADA DOS ÓRGÃOS CONVENIADOS
    # =========================================================================
    orgaos_busca = request.GET.get('q_orgao', '').strip()
    orgaos_status = request.GET.get('status_orgao', 'all').strip()

    orgaos_qs = Orgao.objects.all().order_by('nome')
    if orgaos_busca:
        orgaos_qs = orgaos_qs.filter(Q(nome__icontains=orgaos_busca) | Q(sigla__icontains=orgaos_busca) | Q(descricao__icontains=orgaos_busca))
    if orgaos_status == 'ativos':
        orgaos_qs = orgaos_qs.filter(ativo=True)
    elif orgaos_status == 'inativos':
        orgaos_qs = orgaos_qs.filter(ativo=False)

    orgaos_cards = []
    for org in orgaos_qs:
        alunos_orgao_count = Aluno.objects.ativos().filter(orgao=org).count()
        pais_orgao_count = Aluno.objects.ativos().filter(
            Q(orgao_responsavel=org) | Q(orgao_responsavel_2=org)
        ).count()
        pct_orgao = round((alunos_orgao_count / total_alunos_ativos * 100), 1) if total_alunos_ativos > 0 else 0

        orgaos_cards.append({
            'obj': org,
            'id': org.id,
            'nome': org.nome,
            'sigla': org.sigla or org.nome,
            'descricao': org.descricao or '',
            'ativo': org.ativo,
            'criado_em': org.criado_em,
            'atualizado_em': org.atualizado_em,
            'count_alunos': alunos_orgao_count,
            'count_pais': pais_orgao_count,
            'pct_alunos': pct_orgao,
        })

    # =========================================================================
    # 3. GESTÃO DO CALENDÁRIO ESCOLAR & DIAS NÃO LETIVOS / FERIADOS / RECESSOS
    # =========================================================================
    selected_year = request.GET.get('ano_feriado', str(current_year)).strip()
    try:
        selected_year_int = int(selected_year)
    except ValueError:
        selected_year_int = current_year

    feriados_qs = DiaNaoLetivo.objects.filter(
        data_inicio__year=selected_year_int
    ).select_related('turma', 'registrado_por').order_by('data_inicio')

    feriados_lista = []
    for fer in feriados_qs:
        is_intervalo = fer.data_inicio != fer.data_fim
        feriados_lista.append({
            'id': fer.id,
            'tipo': fer.tipo,
            'tipo_display': fer.get_tipo_display(),
            'descricao': fer.descricao,
            'data_inicio': fer.data_inicio,
            'data_fim': fer.data_fim,
            'data_inicio_formatada': fer.data_inicio.strftime('%d/%m/%Y'),
            'data_fim_formatada': fer.data_fim.strftime('%d/%m/%Y'),
            'data_inicio_iso': fer.data_inicio.isoformat(),
            'data_fim_iso': fer.data_fim.isoformat(),
            'is_intervalo': is_intervalo,
            'turma': fer.turma,
            'turma_nome': fer.turma.nome if fer.turma else 'Todas as Salas (Geral)',
            'registrado_por': fer.registrado_por.get_full_name() or fer.registrado_por.username if fer.registrado_por else 'Sistema',
            'criado_em': fer.criado_em,
        })

    # =========================================================================
    # 4. GESTÃO DE TURMAS & SALAS DE AULA
    # =========================================================================
    turmas_qs = Turma.objects.filter(ativo=True).prefetch_related('professores', 'auxiliares').order_by('nome')
    turmas_cards = []
    for t in turmas_qs:
        alunos_turma = t.alunos.ativos()
        turmas_cards.append({
            'id': t.id,
            'nome': t.nome,
            'faixa_etaria': t.faixa_etaria or '',
            'total_alunos': alunos_turma.count(),
            'professores': t.get_professores_display() or 'Nenhum professor vinculado',
            'auxiliares': t.get_auxiliares_display() or 'Nenhum auxiliar vinculado',
            'professores_list': [p.get_full_name() or p.username for p in t.professores.all()],
            'auxiliares_list': [a.get_full_name() or a.username for a in t.auxiliares.all()],
        })

    # =========================================================================
    # 5. RESUMO DE USUÁRIOS
    # =========================================================================
    usuarios_recentes = User.objects.filter(is_active=True).order_by('-date_joined')[:12]

    context = {
        'active_tab': 'administracao',
        'subtab': active_tab,
        'today': today.isoformat(),
        'current_year': current_year,
        'selected_year': selected_year_int,
        'available_years': [2024, 2025, 2026, 2027],
        'metrics': {
            'total_alunos_ativos': total_alunos_ativos,
            'total_alunos_cadastrados': total_alunos_cadastrados,
            'total_alunos_conveniados': total_alunos_conveniados,
            'total_alunos_sem_orgao': total_alunos_sem_orgao,
            'total_turmas': total_turmas,
            'total_orgaos': total_orgaos,
            'total_orgaos_ativos': total_orgaos_ativos,
            'total_usuarios_ativos': total_usuarios_ativos,
            'total_feriados_ano': total_feriados_ano,
            'usuarios_por_role': usuarios_por_role,
        },
        'orgaos_cards': orgaos_cards,
        'orgaos_busca': orgaos_busca,
        'orgaos_status': orgaos_status,
        'feriados_lista': feriados_lista,
        'tipo_dias_choices': TipoDiaNaoLetivo.choices,
        'turmas_cards': turmas_cards,
        'turmas': turmas_qs,
        'usuarios_recentes': usuarios_recentes,
    }
    return render(request, 'core/central_administrativa.html', context)


@login_required
@diretor_required
@require_POST
def salvar_orgao_api(request):
    """
    Cria ou atualiza um Órgão Conveniado via formulário AJAX / JSON.
    """
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        orgao_id = data.get('orgao_id')
        nome = data.get('nome', '').strip()
        sigla = data.get('sigla', '').strip()
        descricao = data.get('descricao', '').strip()
        ativo = data.get('ativo', True)
        if isinstance(ativo, str):
            ativo = ativo.lower() in ['true', '1', 'on', 'yes']

        if not nome:
            return JsonResponse({'success': False, 'error': 'O nome do órgão é obrigatório.'}, status=400)

        if orgao_id and str(orgao_id).isdigit():
            orgao = get_object_or_404(Orgao, id=int(orgao_id))
            orgao.nome = nome
            orgao.sigla = sigla
            orgao.descricao = descricao
            orgao.ativo = ativo
            orgao.save()
            msg = f'Órgão "{orgao.sigla or orgao.nome}" atualizado com sucesso!'
        else:
            if Orgao.objects.filter(nome__iexact=nome).exists():
                return JsonResponse({'success': False, 'error': f'Já existe um órgão cadastrado com o nome "{nome}".'}, status=400)
            if sigla and Orgao.objects.filter(sigla__iexact=sigla).exists():
                return JsonResponse({'success': False, 'error': f'Já existe um órgão cadastrado com a sigla "{sigla}".'}, status=400)

            orgao = Orgao.objects.create(
                nome=nome,
                sigla=sigla,
                descricao=descricao,
                ativo=ativo
            )
            msg = f'Órgão "{orgao.sigla or orgao.nome}" cadastrado com sucesso!'

        return JsonResponse({
            'success': True,
            'message': msg,
            'orgao': {
                'id': orgao.id,
                'nome': orgao.nome,
                'sigla': orgao.sigla,
                'descricao': orgao.descricao,
                'ativo': orgao.ativo
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Falha ao salvar órgão: {str(e)}'}, status=500)


@login_required
@diretor_required
@require_POST
def toggle_orgao_status_api(request, orgao_id):
    """
    Alterna o status Ativo/Inativo de um Órgão Conveniado.
    """
    try:
        orgao = get_object_or_404(Orgao, id=orgao_id)
        orgao.ativo = not orgao.ativo
        orgao.save()
        status_txt = "ativado" if orgao.ativo else "desativado"
        return JsonResponse({
            'success': True,
            'ativo': orgao.ativo,
            'message': f'Órgão "{orgao.sigla or orgao.nome}" foi {status_txt} com sucesso!'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Falha ao alternar status: {str(e)}'}, status=500)


@login_required
@diretor_required
@require_POST
def excluir_orgao_api(request, orgao_id):
    """
    Exclui um Órgão Conveniado caso não existam alunos ou responsáveis vinculados a ele.
    """
    try:
        orgao = get_object_or_404(Orgao, id=orgao_id)

        vinculos_alunos = Aluno.objects.filter(orgao=orgao).count()
        vinculos_pais = Aluno.objects.filter(Q(orgao_responsavel=orgao) | Q(orgao_responsavel_2=orgao)).count()
        total_vinculos = vinculos_alunos + vinculos_pais

        if total_vinculos > 0:
            return JsonResponse({
                'success': False,
                'error': (
                    f'Não é possível excluir o órgão "{orgao.nome}", pois existem '
                    f'{vinculos_alunos} aluno(s) e {vinculos_pais} responsável(eis) vinculados a ele. '
                    f'Para manter a integridade dos históricos, você pode desativá-lo em vez de excluir.'
                )
            }, status=400)

        nome_excluido = orgao.nome
        orgao.delete()
        return JsonResponse({
            'success': True,
            'message': f'Órgão "{nome_excluido}" excluído com sucesso do sistema.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Falha ao excluir órgão: {str(e)}'}, status=500)
