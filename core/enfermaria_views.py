import json
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import models

from presencas.models import Aluno, Turma, AtendimentoEnfermaria
from presencas.services import registrar_atendimento_enfermaria


@login_required
def enfermaria_dashboard_view(request):
    """
    Dashboard do Módulo III: Enfermaria.
    Exibe indicadores clínicos, filtros de período e listagem dos atendimentos.
    """
    today = timezone.localdate()
    
    # 1. Filtros de Período e Turma
    preset = request.GET.get('preset', '').strip()
    date_start_str = request.GET.get('date_start', '').strip()
    date_end_str = request.GET.get('date_end', '').strip()
    classroom_filter = request.GET.get('classroom', '').strip()
    search_q = request.GET.get('q', '').strip()

    # Define datas padrão (se não fornecidas)
    if preset == 'today':
        date_start = today
        date_end = today
    elif preset == '7':
        date_start = today - timedelta(days=7)
        date_end = today
    elif preset == '30':
        date_start = today - timedelta(days=30)
        date_end = today
    elif preset == 'month' or preset == 'thisMonth':
        date_start = today.replace(day=1)
        next_month = (today.replace(day=28) + timedelta(days=4))
        date_end = next_month - timedelta(days=next_month.day)
    elif preset == 'quarter':
        date_start = today - timedelta(days=90)
        date_end = today
    elif preset == 'year' or preset == 'thisYear':
        date_start = date(today.year, 1, 1)
        date_end = date(today.year, 12, 31)
    else:
        try:
            date_start = date.fromisoformat(date_start_str) if date_start_str else today.replace(day=1)
        except ValueError:
            date_start = today.replace(day=1)
        
        try:
            if date_end_str:
                date_end = date.fromisoformat(date_end_str)
            else:
                next_month = (today.replace(day=28) + timedelta(days=4))
                date_end = next_month - timedelta(days=next_month.day)
        except ValueError:
            next_month = (today.replace(day=28) + timedelta(days=4))
            date_end = next_month - timedelta(days=next_month.day)

    # 2. Query Base de Atendimentos Ativos (Soft-Delete Filtrado)
    qs = AtendimentoEnfermaria.objects.ativos().select_related(
        'aluno', 'aluno__turma', 'registrado_por'
    ).order_by('-data_atendimento', '-horario', '-id')

    # Aplicação dos Filtros na listagem
    atendimentos_filtrados = qs.filter(data_atendimento__range=(date_start, date_end))

    if classroom_filter:
        atendimentos_filtrados = atendimentos_filtrados.filter(aluno__turma__nome__iexact=classroom_filter)

    if search_q:
        atendimentos_filtrados = atendimentos_filtrados.filter(
            models.Q(aluno__nome__icontains=search_q) |
            models.Q(motivo__icontains=search_q) |
            models.Q(motivo_detalhado__icontains=search_q) |
            models.Q(cid__icontains=search_q) |
            models.Q(observacoes_medicas__icontains=search_q)
        )

    # 3 Cards de Indicadores do Período Filtrado
    cards_metrics = {
        'total_atendimentos': atendimentos_filtrados.count(),
        'saidas_imediatas': atendimentos_filtrados.filter(saida_imediata=True).count(),
        'afastamentos': atendimentos_filtrados.filter(retornara_dia_seguinte=False).count(),
    }

    # 3. Lista de Alunos e Turmas para os seletores
    turmas = Turma.objects.filter(ativo=True).order_by('nome')
    alunos_ativos = Aluno.objects.ativos().select_related('turma').order_by('turma__nome', 'nome')

    # Dicionário JSON leve para hidratação imediata do prontuário no modal
    alunos_prontuario_map = {}
    for a in alunos_ativos:
        alunos_prontuario_map[str(a.id)] = {
            'id': a.id,
            'nome': a.nome,
            'turma_nome': a.turma.nome if a.turma else 'Sem Sala',
            'turno': a.get_turno_display() if hasattr(a, 'get_turno_display') else str(a.turno),
            'has_acompanhamento': a.has_acompanhamento,
            'acompanhamento_obs': a.acompanhamento_obs or '',
            'acompanhamento_dias': a.acompanhamento_dias or '',
            'alergias': [x.strip() for x in a.alergias.split(',') if x.strip()] if a.alergias else [],
            'restricoes_alimentares': [x.strip() for x in a.restricoes_alimentares.split(',') if x.strip()] if a.restricoes_alimentares else [],
            'comorbidades': [x.strip() for x in a.comorbidades.split(',') if x.strip()] if a.comorbidades else [],
            'responsavel_nome': a.nome_responsavel or '',
            'responsavel_tel': a.telefone_responsavel or '',
        }

    # Dicionário JSON leve de atendimentos para o modal de Ficha Completa
    atendimentos_map = {}
    for at in atendimentos_filtrados:
        atendimentos_map[str(at.id)] = {
            'id': at.id,
            'aluno_nome': at.aluno.nome,
            'turma_nome': at.aluno.turma.nome if at.aluno.turma else 'Sem Sala',
            'turno': at.aluno.get_turno_display() if hasattr(at.aluno, 'get_turno_display') else str(at.aluno.turno),
            'responsavel_nome': at.aluno.nome_responsavel or 'Não informado',
            'responsavel_tel': at.aluno.telefone_responsavel or 'Não informado',
            'alergias': [x.strip() for x in at.aluno.alergias.split(',') if x.strip()] if at.aluno.alergias else [],
            'restricoes': [x.strip() for x in at.aluno.restricoes_alimentares.split(',') if x.strip()] if at.aluno.restricoes_alimentares else [],
            'comorbidades': [x.strip() for x in at.aluno.comorbidades.split(',') if x.strip()] if at.aluno.comorbidades else [],
            'has_acompanhamento': at.aluno.has_acompanhamento,
            'acompanhamento_obs': at.aluno.acompanhamento_obs or '',
            'acompanhamento_dias': at.aluno.acompanhamento_dias or '',
            'data_atendimento': at.data_atendimento.strftime('%d/%m/%Y'),
            'horario': at.horario.strftime('%H:%M') if at.horario else '',
            'motivo': at.motivo,
            'motivo_detalhado': at.motivo_detalhado or '',
            'cid': at.cid or '',
            'saida_imediata': at.saida_imediata,
            'retornara_dia_seguinte': at.retornara_dia_seguinte,
            'data_retorno_prevista': at.data_retorno_prevista.strftime('%d/%m/%Y') if at.data_retorno_prevista else '',
            'observacoes_medicas': at.observacoes_medicas or '',
            'documento_url': at.documento_anexo.url if at.documento_anexo else '',
            'registrado_por': at.registrado_por.get_full_name() or at.registrado_por.username if at.registrado_por else 'Sistema',
            'criado_em': timezone.localtime(at.criado_em).strftime('%d/%m/%Y às %H:%M') if at.criado_em else '',
        }

    # Motivos clínicos mais comuns para sugestão rápida
    motivos_comuns = [
        'Febre / Temperatura Elevada',
        'Queda / Trauma Leve',
        'Dor Abdominal / Cólica',
        'Dor de Cabeça (Cefaleia)',
        'Episódio de Vômito / Náusea',
        'Curativo / Escoriação',
        'Administração de Medicamento',
        'Reação Alérgica Cutânea',
        'Sintomas Gripais / Coriza',
        'Picada de Inseto',
        'Outros'
    ]

    context = {
        'active_tab': 'enfermaria',
        'active_module': 'enfermaria',
        'atendimentos': atendimentos_filtrados,
        'total_filtrado': atendimentos_filtrados.count(),
        'cards': cards_metrics,
        'turmas': turmas,
        'alunos': alunos_ativos,
        'alunos_json': json.dumps(alunos_prontuario_map),
        'atendimentos_json': json.dumps(atendimentos_map),
        'motivos_comuns': motivos_comuns,
        'date_start': date_start.isoformat(),
        'date_end': date_end.isoformat(),
        'classroom_filter': classroom_filter,
        'search_q': search_q,
        'preset': preset,
        'today': today.isoformat(),
    }

    return render(request, 'enfermaria/dashboard.html', context)


@login_required
@require_POST
def enfermaria_novo_atendimento_view(request):
    """
    Processa o formulário de cadastro de novo atendimento clínico.
    Executa automações de saída antecipada e faltas justificadas.
    """
    aluno_id = request.POST.get('aluno_id')
    data_atendimento_str = request.POST.get('data_atendimento')
    horario_str = request.POST.get('horario')
    motivo = request.POST.get('motivo', '').strip()
    motivo_outro = request.POST.get('motivo_outro', '').strip()
    saida_imediata = request.POST.get('saida_imediata') == 'on' or request.POST.get('saida_imediata') == 'true'
    retornara_dia_seguinte = request.POST.get('retornara_dia_seguinte') != 'nao'
    data_retorno_str = request.POST.get('data_retorno_prevista', '').strip()
    observacoes_medicas = request.POST.get('observacoes_medicas', '').strip()
    cid = request.POST.get('cid', '').strip().upper()
    documento_anexo = request.FILES.get('documento_anexo')

    if not aluno_id:
        messages.error(request, "Selecione o aluno atendido.")
        return redirect('core:enfermaria')

    aluno = get_object_or_404(Aluno, id=aluno_id)

    # Trata motivo
    if motivo == 'Outros' and motivo_outro:
        motivo_final = motivo_outro
    elif motivo == 'Outros':
        motivo_final = 'Outros'
    else:
        motivo_final = motivo or 'Atendimento Clínico Geral'

    try:
        data_atendimento = date.fromisoformat(data_atendimento_str) if data_atendimento_str else timezone.localdate()
    except ValueError:
        data_atendimento = timezone.localdate()

    if horario_str:
        try:
            from datetime import time
            parts = horario_str.split(':')
            horario = time(int(parts[0]), int(parts[1]))
        except Exception:
            horario = timezone.localtime().time()
    else:
        horario = timezone.localtime().time()

    data_retorno_prevista = None
    if saida_imediata and not retornara_dia_seguinte and data_retorno_str:
        try:
            data_retorno_prevista = date.fromisoformat(data_retorno_str)
        except ValueError:
            data_retorno_prevista = None

    try:
        atendimento = registrar_atendimento_enfermaria(
            aluno=aluno,
            data_atendimento=data_atendimento,
            horario=horario,
            motivo=motivo_final,
            motivo_detalhado=motivo_outro if motivo != 'Outros' else '',
            saida_imediata=saida_imediata,
            retornara_dia_seguinte=retornara_dia_seguinte,
            data_retorno_prevista=data_retorno_prevista,
            observacoes_medicas=observacoes_medicas,
            cid=cid,
            documento_anexo=documento_anexo,
            registrado_por=request.user
        )
        
        msg = f"Atendimento de {aluno.nome} registrado com sucesso na Enfermaria!"
        if saida_imediata:
            msg += " (Saída antecipada registrada no Caderno SEAMI)"
        if saida_imediata and not retornara_dia_seguinte and data_retorno_prevista:
            msg += f" (Faltas justificadas agendadas até {data_retorno_prevista.strftime('%d/%m/%Y')})"
        
        messages.success(request, msg)
    except Exception as e:
        messages.error(request, f"Erro ao registrar atendimento: {e}")

    return redirect('core:enfermaria')


@login_required
@require_POST
def enfermaria_deletar_atendimento_view(request, atendimento_id):
    """
    Executa o Soft Delete do atendimento de enfermaria.
    Apenas perfis autorizados (Enfermeira, Diretor, Master Admin) podem deletar.
    """
    atendimento = get_object_or_404(AtendimentoEnfermaria, id=atendimento_id)
    
    # Soft delete
    atendimento.soft_delete(user=request.user)
    messages.success(request, f"Atendimento de {atendimento.aluno.nome} removido da listagem.")
    return redirect('core:enfermaria')


@login_required
def enfermaria_aluno_info_api(request, aluno_id):
    """
    API JSON para retornar o prontuário de saúde completo do aluno.
    """
    aluno = get_object_or_404(Aluno, id=aluno_id)
    return JsonResponse({
        'id': aluno.id,
        'nome': aluno.nome,
        'turma_nome': aluno.turma.nome if aluno.turma else 'Sem Sala',
        'turno': aluno.get_turno_display() if hasattr(aluno, 'get_turno_display') else str(aluno.turno),
        'has_acompanhamento': aluno.has_acompanhamento,
        'acompanhamento_obs': aluno.acompanhamento_obs or '',
        'acompanhamento_dias': aluno.acompanhamento_dias or '',
        'alergias': [x.strip() for x in aluno.alergias.split(',') if x.strip()] if aluno.alergias else [],
        'restricoes_alimentares': [x.strip() for x in aluno.restricoes_alimentares.split(',') if x.strip()] if aluno.restricoes_alimentares else [],
        'comorbidades': [x.strip() for x in aluno.comorbidades.split(',') if x.strip()] if aluno.comorbidades else [],
        'responsavel_nome': aluno.nome_responsavel or '',
        'responsavel_tel': aluno.telefone_responsavel or '',
    })
