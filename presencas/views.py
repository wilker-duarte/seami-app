import json
import calendar
from datetime import datetime, date, timedelta
# pyrefly: ignore [missing-import]
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Sum, Count
from .models import (
    Turma, Aluno, RegistroPresenca, StatusPresenca, StatusTurnoPresenca,
    TurnoAluno, LancamentoChamada, DiarioDeClasse, TurnoFiltro,
    TipoOcorrencia, OcorrenciaCaderno, RegistroAmamentacao
)

MONTH_NAMES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

CORES_SALAS = {
    'alegria': {'bg': '#fef3c7', 'color': '#92400e', 'border': '#fde68a', 'emoji': '💛'},
    'carinho': {'bg': '#fce7f3', 'color': '#9d174d', 'border': '#fbcfe8', 'emoji': '💖'},
    'união': {'bg': '#e0e7ff', 'color': '#3730a3', 'border': '#c7d2fe', 'emoji': '💙'},
    'uniao': {'bg': '#e0e7ff', 'color': '#3730a3', 'border': '#c7d2fe', 'emoji': '💙'},
    'amizade': {'bg': '#dcfce7', 'color': '#166534', 'border': '#bbf7d0', 'emoji': '💚'},
    'felicidade': {'bg': '#f3e8ff', 'color': '#6b21a8', 'border': '#e9d5ff', 'emoji': '💜'},
}

@login_required
def lancar_chamada_view(request):
    """
    Tela de Lançamento de Chamada idêntica ao DailyAttendance do SEAMI,
    incluindo Mini-Calendário Mensal, suporte a 'Todas as salas' e
    filtros por turno (Matutino, Vespertino, Integral).
    """
    today = timezone.localdate()
    
    # Parâmetros da Requisição
    date_str = request.GET.get('date', today.isoformat())
    turma_nome = request.GET.get('classroom', 'all')  # Default 'all' ou sala selecionada
    shift_filter = request.GET.get('shift', 'all')

    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = today

    turmas = Turma.objects.filter(ativo=True).order_by('nome')
    is_all_classrooms = (turma_nome == 'all' or turma_nome == '' or turma_nome == 'Todas as salas')
    
    if is_all_classrooms:
        selected_turma = None
    else:
        selected_turma = turmas.filter(nome__iexact=turma_nome).first() or turmas.first()

    # =========================================================================
    # LÓGICA DO CALENDÁRIO MENSAL & DIAS COM CHAMADA LANÇADA
    # =========================================================================
    year = current_date.year
    month = current_date.month
    month_label = f"{MONTH_NAMES_PT[month]} de {year}"

    # Primeiro e último dia do mês exibido
    num_days = calendar.monthrange(year, month)[1]
    first_day_of_month = date(year, month, 1)
    last_day_of_month = date(year, month, num_days)

    # Datas de navegação (mês anterior e próximo)
    prev_month_last_day = first_day_of_month - timedelta(days=1)
    prev_date_str = prev_month_last_day.replace(day=min(current_date.day, prev_month_last_day.day)).isoformat()

    next_month_first_day = last_day_of_month + timedelta(days=1)
    next_num_days = calendar.monthrange(next_month_first_day.year, next_month_first_day.month)[1]
    next_date_str = next_month_first_day.replace(day=min(current_date.day, next_num_days)).isoformat()

    # Busca no banco quais datas deste mês possuem chamadas registradas
    chamadas_qs = RegistroPresenca.objects.filter(
        data__gte=first_day_of_month,
        data__lte=last_day_of_month
    )
    if selected_turma:
        chamadas_qs = chamadas_qs.filter(turma=selected_turma)
    
    datas_com_chamada = set(chamadas_qs.values_list('data', flat=True).distinct())

    # Monta a grade de dias do calendário
    start_weekday = (first_day_of_month.weekday() + 1) % 7
    calendar_days = []
    
    for p in range(start_weekday):
        calendar_days.append({'is_padding': True})

    for day_num in range(1, num_days + 1):
        d_obj = date(year, month, day_num)
        d_iso = d_obj.isoformat()
        has_attendance = d_obj in datas_com_chamada
        calendar_days.append({
            'is_padding': False,
            'day': day_num,
            'date': d_iso,
            'is_selected': d_obj == current_date,
            'is_today': d_obj == today,
            'is_weekend': d_obj.weekday() in (5, 6),
            'has_attendance': has_attendance
        })

    # =========================================================================
    # ALUNOS & REGISTROS DA SALA / TODAS AS SALAS E TURNO SELECIONADOS
    # =========================================================================
    cores_salas = {
        'amizade': {'bg': '#f5f3ff', 'color': '#7c3aed', 'border': '#ddd6fe', 'emoji': '🎨'},
        'união': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'uniao': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'felicidade': {'bg': '#fdf2f8', 'color': '#db2777', 'border': '#fbcfe8', 'emoji': '✨'},
        'carinho': {'bg': '#ecfdf5', 'color': '#059669', 'border': '#a7f3d0', 'emoji': '🧸'},
        'alegria': {'bg': '#eff6ff', 'color': '#2563eb', 'border': '#bfdbfe', 'emoji': '👶'},
    }

    # Alunos matriculados exatamente na data selecionada (respeitando data de entrada e desligamento)
    alunos_no_dia_qs = Aluno.objects.filter(
        Q(data_entrada__isnull=True) | Q(data_entrada__lte=current_date)
    ).filter(
        Q(data_desligamento__isnull=True) | Q(data_desligamento__gte=current_date)
    ).select_related('turma')

    alunos_qs = alunos_no_dia_qs
    if selected_turma:
        alunos_qs = alunos_qs.filter(turma=selected_turma)

    if shift_filter != 'all':
        alunos_qs = alunos_qs.filter(turno__iexact=shift_filter)
            
    alunos_qs = alunos_qs.order_by('nome')

    # Busca Ocorrências do Caderno SEAMI ativas na data (Ausências Programadas: Atestados e Faltas Agendadas)
    ocorrencias_data_qs = OcorrenciaCaderno.objects.filter(
        Q(data=current_date, data_fim__isnull=True) |
        Q(data__lte=current_date, data_fim__gte=current_date) |
        Q(data=current_date)
    ).select_related('aluno')

    # Mapeia ocorrência por aluno_id
    mapa_ocorrencias = {}
    for oc in ocorrencias_data_qs:
        if oc.aluno_id and oc.aluno_id not in mapa_ocorrencias:
            mapa_ocorrencias[oc.aluno_id] = oc

    # Registros de presença existentes para a data
    regs_query = RegistroPresenca.objects.filter(data=current_date)
    if selected_turma:
        regs_query = regs_query.filter(turma=selected_turma)
    registros = {r.aluno_id: r for r in regs_query}

    students_list = []
    total_presentes = 0
    total_faltas = 0
    total_justificadas = 0

    for aluno in alunos_qs:
        reg = registros.get(aluno.id)
        oc_aluno = mapa_ocorrencias.get(aluno.id)

        # Informações de Ausência Programada
        ausencia_info = None
        if oc_aluno:
            dt_inicio_str = oc_aluno.data.strftime('%d/%m/%Y')
            dt_fim_str = oc_aluno.data_fim.strftime('%d/%m/%Y') if oc_aluno.data_fim else dt_inicio_str
            periodo_str = f"({dt_inicio_str} a {dt_fim_str})"

            if oc_aluno.tipo == TipoOcorrencia.ATESTADO:
                tipo_titulo = "Atestado Médico"
                is_atestado = True
                is_falta_agendada = False
            else:
                tipo_titulo = "Falta Agendada"
                is_atestado = False
                is_falta_agendada = True

            ausencia_info = {
                'tipo': oc_aluno.tipo,
                'titulo': tipo_titulo,
                'periodo': periodo_str,
                'is_atestado': is_atestado,
                'is_falta_agendada': is_falta_agendada,
                'motivo': oc_aluno.motivo or oc_aluno.observacao or oc_aluno.cid,
            }

        # Definição do status inicial
        if reg:
            current_status = reg.status
            obs = reg.observacao
        elif oc_aluno:
            if oc_aluno.tipo == TipoOcorrencia.ATESTADO or oc_aluno.justificado:
                current_status = StatusPresenca.JUSTIFICADO
            else:
                current_status = StatusPresenca.AUSENTE
            obs = oc_aluno.motivo or oc_aluno.observacao or 'Ausência programada no Caderno SEAMI'
        else:
            current_status = StatusPresenca.PRESENTE
            obs = ''

        if current_status == StatusPresenca.PRESENTE:
            total_presentes += 1
        elif current_status == StatusPresenca.AUSENTE:
            total_faltas += 1
        elif current_status == StatusPresenca.JUSTIFICADO:
            total_justificadas += 1

        status_m = reg.status_matutino if reg else StatusTurnoPresenca.PENDENTE
        status_v = reg.status_vespertino if reg else StatusTurnoPresenca.PENDENTE

        turma_style = CORES_SALAS.get(aluno.turma.nome.lower().strip(), {'bg': '#f1f5f9', 'color': '#475569', 'border': '#cbd5e1', 'emoji': '🏫'})

        # Identificação de pendência da criança no dia selecionado
        is_pendente = (reg is None)
        motivo_pendencia = 'Chamada não realizada' if is_pendente else ''

        students_list.append({
            'id': aluno.id,
            'nome': aluno.nome,
            'turma_id': aluno.turma.id,
            'turma_nome': aluno.turma.nome,
            'turma_style': turma_style,
            'turno': aluno.get_turno_display(),
            'turno_raw': aluno.turno,
            'has_acompanhamento': aluno.has_acompanhamento,
            'acompanhamento_obs': aluno.acompanhamento_obs,
            'ausencia_programada': ausencia_info,
            'status': current_status,
            'status_matutino': status_m,
            'status_vespertino': status_v,
            'obs': obs,
            'is_pendente': is_pendente,
            'motivo_pendencia': motivo_pendencia
        })

    # =========================================================================
    # STATUS DE LANÇAMENTO: POR TURNO E POR SALA NA DATA SELECIONADA
    # =========================================================================
    all_alunos_scope = alunos_no_dia_qs
    if selected_turma:
        all_alunos_scope = all_alunos_scope.filter(turma=selected_turma)

    saved_student_ids = set(RegistroPresenca.objects.filter(
        data=current_date, 
        aluno_id__in=all_alunos_scope.values_list('id', flat=True)
    ).values_list('aluno_id', flat=True))

    matutino_ids = set(all_alunos_scope.filter(turno__iexact='matutino').values_list('id', flat=True))
    vespertino_ids = set(all_alunos_scope.filter(turno__iexact='vespertino').values_list('id', flat=True))
    integral_ids = set(all_alunos_scope.filter(turno__iexact='integral').values_list('id', flat=True))

    shifts_saved_status = {
        'matutino': {
            'has_students': len(matutino_ids) > 0,
            'is_saved': len(matutino_ids) > 0 and len(matutino_ids.intersection(saved_student_ids)) == len(matutino_ids),
            'total': len(matutino_ids),
            'salvos': len(matutino_ids.intersection(saved_student_ids))
        },
        'vespertino': {
            'has_students': len(vespertino_ids) > 0,
            'is_saved': len(vespertino_ids) > 0 and len(vespertino_ids.intersection(saved_student_ids)) == len(vespertino_ids),
            'total': len(vespertino_ids),
            'salvos': len(vespertino_ids.intersection(saved_student_ids))
        },
        'integral': {
            'has_students': len(integral_ids) > 0,
            'is_saved': len(integral_ids) > 0 and len(integral_ids.intersection(saved_student_ids)) == len(integral_ids),
            'total': len(integral_ids),
            'salvos': len(integral_ids.intersection(saved_student_ids))
        },
    }

    # Status geral de chamada por sala na data selecionada
    all_saved_in_date_ids = set(RegistroPresenca.objects.filter(
        data=current_date,
        aluno_id__in=alunos_no_dia_qs.values_list('id', flat=True)
    ).values_list('aluno_id', flat=True))

    total_salas_count = turmas.count()
    salas_status_list = []
    for t in turmas:
        t_alunos_ids = set(alunos_no_dia_qs.filter(turma=t).values_list('id', flat=True))
        t_salvos = len(t_alunos_ids.intersection(all_saved_in_date_ids))
        t_is_saved = (len(t_alunos_ids) > 0 and t_salvos == len(t_alunos_ids))
        salas_status_list.append({
            'turma': t,
            'is_saved': t_is_saved,
            'total_alunos': len(t_alunos_ids),
            'total_salvos': t_salvos,
            'turma_style': CORES_SALAS.get(t.nome.lower().strip(), {'bg': '#f1f5f9', 'color': '#475569', 'border': '#cbd5e1', 'emoji': '🏫'})
        })

    salas_lancadas_count = sum(1 for s in salas_status_list if s['is_saved'])

    if selected_turma:
        is_attendance_saved = next((s['is_saved'] for s in salas_status_list if s['turma'].id == selected_turma.id), False)
    else:
        is_attendance_saved = (salas_lancadas_count == total_salas_count and total_salas_count > 0)

    total_alunos = len(students_list)
    taxa_presenca = round((total_presentes / total_alunos) * 100) if total_alunos > 0 else 100

    # =========================================================================
    # PENDÊNCIAS EXCLUSIVAS DO DIA DA CHAMADA
    # =========================================================================
    alunos_pendentes_dia = [s for s in students_list if s['is_pendente']]
    total_pendentes_dia = len(alunos_pendentes_dia)
    salas_pendentes_dia = [s for s in salas_status_list if not s['is_saved']]

    context = {
        'turmas': turmas,
        'selected_turma': selected_turma,
        'is_all_classrooms': is_all_classrooms,
        'current_classroom_param': 'all' if is_all_classrooms else selected_turma.nome,
        'attendance_date': current_date.isoformat(),
        'attendance_date_formatted': current_date.strftime('%d/%m/%Y'),
        'month_label': month_label,
        'prev_date_str': prev_date_str,
        'next_date_str': next_date_str,
        'calendar_days': calendar_days,
        'shift_filter': shift_filter,
        'students_list': students_list,
        'total_alunos': total_alunos,
        'total_presentes': total_presentes,
        'total_faltas': total_faltas,
        'total_justificadas': total_justificadas,
        'taxa_presenca': taxa_presenca,
        'shifts_saved_status': shifts_saved_status,
        'is_attendance_saved': is_attendance_saved,
        'salas_lancadas_count': salas_lancadas_count,
        'total_salas_count': total_salas_count,
        'salas_status_list': salas_status_list,
        'alunos_pendentes_dia': alunos_pendentes_dia,
        'total_pendentes_dia': total_pendentes_dia,
        'salas_pendentes_dia': salas_pendentes_dia,
        'active_tab': 'attendance',
        'active_module': 'lancamento',
    }
    return render(request, 'presencas/lancar_chamada.html', context)


@login_required
@require_POST
def salvar_chamada_lote_view(request):
    """
    Salva a sessão de Diário de Classe e atualiza os Registros de Presença
    de forma 100% relacional e atômica no PostgreSQL.
    """
    try:
        data = json.loads(request.body)
        turma_id = data.get('turma_id')
        data_chamada_str = data.get('date')
        shift = data.get('shift', 'all')
        items = data.get('items', [])
        obs_geral = data.get('obs_geral', '')

        if not data_chamada_str:
            return JsonResponse({'success': False, 'error': 'Data obrigatória'}, status=400)

        data_chamada = datetime.strptime(data_chamada_str, '%Y-%m-%d').date()

        from django.db import transaction
        with transaction.atomic():
            salvos = 0
            for item in items:
                aluno_id = item.get('student_id')
                status = item.get('status', StatusPresenca.PRESENTE)
                obs = item.get('obs', '')

                aluno = Aluno.objects.filter(id=aluno_id).select_related('turma').first()
                if not aluno:
                    continue

                aluno_turma = aluno.turma

                # Obtém ou cria a sessão de Diário de Classe para a turma daquele aluno
                diario, _ = DiarioDeClasse.objects.get_or_create(
                    turma=aluno_turma,
                    data=data_chamada,
                    turno=shift,
                    defaults={
                        'registrado_por': request.user,
                        'observacao': obs_geral
                    }
                )

                reg, _ = RegistroPresenca.objects.get_or_create(
                    aluno=aluno,
                    data=data_chamada,
                    defaults={
                        'diario_classe': diario,
                        'turma': aluno_turma,
                        'registrado_por': request.user
                    }
                )

                reg.diario_classe = diario
                reg.turma = aluno_turma
                reg.registrado_por = request.user

                turno_aluno = (aluno.turno or 'integral').lower()

                # Atualiza os status conforme o turno em que a chamada foi realizada
                if shift == 'matutino':
                    reg.status_matutino = status
                    if turno_aluno == 'matutino':
                        reg.status_vespertino = StatusTurnoPresenca.NA
                    elif not reg.status_vespertino:
                        reg.status_vespertino = StatusTurnoPresenca.PENDENTE
                elif shift == 'vespertino':
                    reg.status_vespertino = status
                    if turno_aluno == 'vespertino':
                        reg.status_matutino = StatusTurnoPresenca.NA
                    elif not reg.status_matutino:
                        reg.status_matutino = StatusTurnoPresenca.PENDENTE
                else:  # all / integral
                    if turno_aluno == 'matutino':
                        reg.status_matutino = status
                        reg.status_vespertino = StatusTurnoPresenca.NA
                    elif turno_aluno == 'vespertino':
                        reg.status_matutino = StatusTurnoPresenca.NA
                        reg.status_vespertino = status
                    else:  # integral
                        reg.status_matutino = status
                        reg.status_vespertino = status

                reg.calcular_status_e_observacao(custom_obs=obs)
                reg.save()
                salvos += 1

        return JsonResponse({
            'success': True,
            'message': f'Chamada salva com sucesso para {salvos} crianças!',
            'saved_count': salvos
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def consulta_chamada_view(request):
    """
    Tela de Registros e Exportação & Relatórios de Frequência do Módulo I:
    Abas:
    1. 'consulta' -> Registros e Exportação (Histórico de Presenças com filtros)
    2. 'relatorios' -> Relatórios & Situação do Aluno (Frequência Diária Geral, Semanal/Mensal e Situação Individual)
    """
    today = timezone.localdate()
    frequency_tab = request.GET.get('tab', 'consulta')  # 'consulta' | 'relatorios'
    turmas = Turma.objects.filter(ativo=True).order_by('nome')
    alunos_todos = Aluno.objects.filter(ativo=True).select_related('turma').order_by('nome')

    # Dados da aba 1: Consulta / Histórico de Presenças
    filter_type = request.GET.get('filter_type', 'month')  # 'custom' | 'month'
    month_ref = request.GET.get('month_ref', f"{today.year}-{today.month:02d}")
    turma_id = request.GET.get('classroom', '')
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()

    if filter_type == 'month':
        try:
            y, m = map(int, month_ref.split('-'))
            start_date = date(y, m, 1)
            num_days = calendar.monthrange(y, m)[1]
            end_date = date(y, m, num_days)
        except Exception:
            start_date = today.replace(day=1)
            end_date = today
            month_ref = f"{today.year}-{today.month:02d}"
        date_start_str = start_date.isoformat()
        date_end_str = end_date.isoformat()
    else:
        date_start_str = request.GET.get('date_start', (today.replace(day=1)).isoformat())
        date_end_str = request.GET.get('date_end', today.isoformat())
        try:
            start_date = datetime.strptime(date_start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(date_end_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = today.replace(day=1)
            end_date = today

    registros = RegistroPresenca.objects.filter(
        data__gte=start_date,
        data__lte=end_date
    ).select_related('aluno', 'turma', 'registrado_por')

    if turma_id:
        registros = registros.filter(
            Q(turma_id=turma_id if turma_id.isdigit() else None) | Q(turma__nome__iexact=turma_id)
        )
    if status_filter:
        registros = registros.filter(status=status_filter)
    if search_query:
        registros = registros.filter(
            Q(aluno__nome__icontains=search_query) |
            Q(turma__nome__icontains=search_query) |
            Q(observacao__icontains=search_query)
        )

    registros = registros.order_by('-data', 'aluno__nome')

    # Dados da aba 2: Relatórios & Situação do Aluno (Frequência Diária Geral)
    report_daily_date_str = request.GET.get('daily_date', today.isoformat())
    try:
        report_daily_date = datetime.strptime(report_daily_date_str, '%Y-%m-%d').date()
    except ValueError:
        report_daily_date = today

    daily_regs = RegistroPresenca.objects.filter(data=report_daily_date)
    daily_present = daily_regs.filter(status=StatusPresenca.PRESENTE).count()
    daily_lack = daily_regs.filter(status=StatusPresenca.AUSENTE).count()
    daily_justified = daily_regs.filter(status=StatusPresenca.JUSTIFICADO).count()
    daily_total = daily_present + daily_lack + daily_justified
    daily_rate = round((daily_present / daily_total) * 100) if daily_total > 0 else 0

    daily_stats = {
        'date': report_daily_date,
        'date_str': report_daily_date.isoformat(),
        'present': daily_present,
        'lack': daily_lack,
        'justified': daily_justified,
        'total': daily_total,
        'rate': daily_rate,
        'has_data': daily_total > 0
    }

    # 2. Relatório Semanal e Mensal (com suporte a filtro por sala)
    weekly_room = request.GET.get('weekly_room', 'all')
    weekly_regs_scope = RegistroPresenca.objects.all()
    if weekly_room != 'all' and weekly_room:
        weekly_regs_scope = weekly_regs_scope.filter(
            Q(turma_id=weekly_room if str(weekly_room).isdigit() else None) | Q(turma__nome__iexact=weekly_room)
        )

    # Semanas (últimas 8 semanas a partir da segunda-feira atual)
    weekly_stats_list = []
    curr_weekday = today.weekday()  # 0 = Segunda
    curr_monday = today - timedelta(days=curr_weekday)

    for w_idx in range(8):
        w_start = curr_monday - timedelta(weeks=w_idx)
        w_end = w_start + timedelta(days=4)  # Segunda a Sexta
        w_regs = weekly_regs_scope.filter(data__gte=w_start, data__lte=w_end)
        w_pres = w_regs.filter(status=StatusPresenca.PRESENTE).count()
        w_tot = w_regs.count()
        if w_tot > 0:
            w_rate = round((w_pres / w_tot) * 100)
            weekly_stats_list.append({
                'week': f"{w_start.strftime('%d/%m')} a {w_end.strftime('%d/%m/%Y')}",
                'present': w_pres,
                'total': w_tot,
                'rate': w_rate
            })

    # Relatório Mensal consolidado
    monthly_stats_list = []
    for i in range(7, -1, -1):
        target_m = today.month - i
        target_y = today.year
        while target_m <= 0:
            target_m += 12
            target_y -= 1
        m_start = date(target_y, target_m, 1)
        m_days = calendar.monthrange(target_y, target_m)[1]
        m_end = date(target_y, target_m, m_days)
        m_regs = weekly_regs_scope.filter(data__gte=m_start, data__lte=m_end)
        m_pres = m_regs.filter(status=StatusPresenca.PRESENTE).count()
        m_tot = m_regs.count()
        if m_tot > 0:
            m_rate = round((m_pres / m_tot) * 100)
            monthly_stats_list.append({
                'month': f"{MONTH_NAMES_PT[target_m]} / {target_y}",
                'present': m_pres,
                'total': m_tot,
                'rate': m_rate
            })

    # Situação Individual do Aluno Selecionado
    selected_student_id = request.GET.get('student_id')
    individual_stats = None
    if selected_student_id:
        student_obj = Aluno.objects.filter(id=selected_student_id).select_related('turma').first()
        if student_obj:
            std_regs = RegistroPresenca.objects.filter(aluno=student_obj)
            std_pres = std_regs.filter(status=StatusPresenca.PRESENTE).count()
            std_lack = std_regs.filter(status=StatusPresenca.AUSENTE).count()
            std_just = std_regs.filter(status=StatusPresenca.JUSTIFICADO).count()
            std_tot = std_regs.count()
            std_rate = round((std_pres / std_tot) * 100) if std_tot > 0 else 100
            individual_stats = {
                'aluno': student_obj,
                'present': std_pres,
                'lack': std_lack,
                'justified': std_just,
                'total': std_tot,
                'rate': std_rate
            }

    context = {
        'frequency_tab': frequency_tab,
        'registros': registros[:300],
        'total_registros': registros.count(),
        'turmas': turmas,
        'alunos_todos': alunos_todos,
        'filter_type': filter_type,
        'month_ref': month_ref,
        'date_start': start_date.isoformat(),
        'date_end': end_date.isoformat(),
        'selected_classroom': int(turma_id) if turma_id.isdigit() else turma_id,
        'selected_status': status_filter,
        'search_query': search_query,
        'daily_stats': daily_stats,
        'weekly_stats_list': weekly_stats_list,
        'weekly_room': weekly_room,
        'monthly_stats_list': monthly_stats_list,
        'individual_stats': individual_stats,
        'selected_student_id': int(selected_student_id) if selected_student_id and selected_student_id.isdigit() else None,
        'active_tab': 'attendance',
        'active_module': 'relatorios' if frequency_tab == 'relatorios' else 'consulta',
    }
    return render(request, 'presencas/consulta_chamada.html', context)


@login_required
def lista_alunos_view(request):
    """
    Página /alunos/ com tabela completa de crianças, salas temáticas,
    destaques de turnos, status e alertas de desativação futura (warning).
    """
    today = timezone.localdate()
    search = request.GET.get('q', '').strip()
    classroom_filter = request.GET.get('classroom', '').strip()
    shift_filter = request.GET.get('shift', '').strip()
    status_filter = request.GET.get('status', 'all').strip()

    # Tratamento de POST para Cadastrar / Editar Aluno
    if request.method == 'POST':
        action = request.POST.get('action')
        aluno_id = request.POST.get('aluno_id')
        
        if action in ['create', 'update']:
            nome = request.POST.get('nome', '').strip()
            turma_id = request.POST.get('turma')
            turno = request.POST.get('turno', TurnoAluno.INTEGRAL)
            data_entrada_str = request.POST.get('data_entrada')
            data_desligamento_str = request.POST.get('data_desligamento')
            has_acompanhamento = request.POST.get('has_acompanhamento') == 'on'
            acompanhamento_obs = request.POST.get('acompanhamento_obs', '').strip()
            # Dias da semana: checkboxes múltiplos (seg, ter, qua, qui, sex)
            acompanhamento_dias_list = request.POST.getlist('acompanhamento_dias')
            acompanhamento_dias = ','.join(acompanhamento_dias_list)

            # Alergias (Múltipla seleção + Outros)
            alergias_list = [x.strip() for x in request.POST.getlist('alergias') if x.strip() and x != 'Outros']
            alergias_outro = request.POST.get('alergias_outro', '').strip()
            if alergias_outro:
                alergias_list.extend([x.strip() for x in alergias_outro.split(',') if x.strip()])
            alergias = ', '.join(dict.fromkeys(alergias_list))

            # Restrições Alimentares (Múltipla seleção + Outros)
            restricoes_list = [x.strip() for x in request.POST.getlist('restricoes_alimentares') if x.strip() and x != 'Outros']
            restricoes_outro = request.POST.get('restricoes_outro', '').strip()
            if restricoes_outro:
                restricoes_list.extend([x.strip() for x in restricoes_outro.split(',') if x.strip()])
            restricoes_alimentares = ', '.join(dict.fromkeys(restricoes_list))

            # Comorbidades / Condições de Saúde (Múltipla seleção + Outros)
            comorbidades_list = [x.strip() for x in request.POST.getlist('comorbidades') if x.strip() and x != 'Outros']
            comorbidades_outro = request.POST.get('comorbidades_outro', '').strip()
            if comorbidades_outro:
                comorbidades_list.extend([x.strip() for x in comorbidades_outro.split(',') if x.strip()])
            comorbidades = ', '.join(dict.fromkeys(comorbidades_list))

            nome_responsavel = request.POST.get('nome_responsavel', '').strip()
            telefone_responsavel = request.POST.get('telefone_responsavel', '').strip()
            ativo = request.POST.get('ativo') == 'on'

            data_entrada = datetime.strptime(data_entrada_str, '%Y-%m-%d').date() if data_entrada_str else today
            data_desligamento = datetime.strptime(data_desligamento_str, '%Y-%m-%d').date() if data_desligamento_str else None
            turma = get_object_or_404(Turma, id=turma_id)

            if action == 'create':
                Aluno.objects.create(
                    nome=nome,
                    turma=turma,
                    turno=turno,
                    data_entrada=data_entrada,
                    data_desligamento=data_desligamento,
                    has_acompanhamento=has_acompanhamento,
                    acompanhamento_obs=acompanhamento_obs,
                    acompanhamento_dias=acompanhamento_dias,
                    alergias=alergias,
                    restricoes_alimentares=restricoes_alimentares,
                    comorbidades=comorbidades,
                    nome_responsavel=nome_responsavel,
                    telefone_responsavel=telefone_responsavel,
                    ativo=ativo
                )
            elif action == 'update' and aluno_id:
                aluno = get_object_or_404(Aluno, id=aluno_id)
                aluno.nome = nome
                aluno.turma = turma
                aluno.turno = turno
                aluno.data_entrada = data_entrada
                aluno.data_desligamento = data_desligamento
                aluno.has_acompanhamento = has_acompanhamento
                aluno.acompanhamento_obs = acompanhamento_obs
                aluno.acompanhamento_dias = acompanhamento_dias
                aluno.alergias = alergias
                aluno.restricoes_alimentares = restricoes_alimentares
                aluno.comorbidades = comorbidades
                aluno.nome_responsavel = nome_responsavel
                aluno.telefone_responsavel = telefone_responsavel
                aluno.ativo = ativo
                aluno.save()

            return redirect(request.get_full_path())

        elif action == 'toggle_active' and aluno_id:
            aluno = get_object_or_404(Aluno, id=aluno_id)
            deactivation_date_str = request.POST.get('deactivation_date')
            if aluno.ativo:
                aluno.ativo = False
                if deactivation_date_str:
                    aluno.data_desligamento = datetime.strptime(deactivation_date_str, '%Y-%m-%d').date()
                else:
                    aluno.data_desligamento = today
            else:
                aluno.ativo = True
                aluno.data_desligamento = None
            aluno.save()
            return redirect(request.get_full_path())

    alunos_qs = Aluno.objects.all().select_related('turma')

    if search:
        alunos_qs = alunos_qs.filter(
            Q(nome__icontains=search) |
            Q(nome_responsavel__icontains=search) |
            Q(telefone_responsavel__icontains=search)
        )

    if classroom_filter:
        alunos_qs = alunos_qs.filter(
            Q(turma__nome__iexact=classroom_filter) | Q(turma_id=classroom_filter if classroom_filter.isdigit() else None)
        )

    if shift_filter and shift_filter != 'all':
        alunos_qs = alunos_qs.filter(turno=shift_filter)

    if status_filter == 'active':
        alunos_qs = alunos_qs.filter(ativo=True)
    elif status_filter == 'inactive':
        alunos_qs = alunos_qs.filter(ativo=False)

    alunos_qs = alunos_qs.order_by('nome')
    turmas_qs = Turma.objects.filter(ativo=True).order_by('nome')

    # Mapeamento de Cores Idênticas ao Dashboard por Sala
    cores_salas = {
        'amizade': {'bg': '#f5f3ff', 'color': '#7c3aed', 'border': '#ddd6fe', 'emoji': '🎨'},
        'união': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'uniao': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'felicidade': {'bg': '#fdf2f8', 'color': '#db2777', 'border': '#fbcfe8', 'emoji': '✨'},
        'carinho': {'bg': '#ecfdf5', 'color': '#059669', 'border': '#a7f3d0', 'emoji': '🧸'},
        'alegria': {'bg': '#eff6ff', 'color': '#2563eb', 'border': '#bfdbfe', 'emoji': '👶'},
    }

    # Prepara lista com metadados de status e desativação futura
    alunos_list = []
    for aluno in alunos_qs:
        nome_lower = aluno.turma.nome.lower().strip()
        turma_style = cores_salas.get(nome_lower, {'bg': '#f1f5f9', 'color': '#475569', 'border': '#cbd5e1', 'emoji': '🏫'})

        # Verifica se o desligamento é futuro (Warning)
        is_desligamento_futuro = bool(aluno.data_desligamento and aluno.data_desligamento > today)
        is_desligamento_passado = bool(aluno.data_desligamento and aluno.data_desligamento <= today)

        alunos_list.append({
            'obj': aluno,
            'id': aluno.id,
            'nome': aluno.nome,
            'turma': aluno.turma,
            'turma_style': turma_style,
            'turno': aluno.get_turno_display(),
            'turno_raw': aluno.turno,
            'data_entrada': aluno.data_entrada,
            'data_desligamento': aluno.data_desligamento,
            'is_desligamento_futuro': is_desligamento_futuro,
            'is_desligamento_passado': is_desligamento_passado,
            'has_acompanhamento': aluno.has_acompanhamento,
            'acompanhamento_obs': aluno.acompanhamento_obs,
            'acompanhamento_dias': aluno.acompanhamento_dias or '',
            'alergias': aluno.alergias or '',
            'restricoes_alimentares': aluno.restricoes_alimentares or '',
            'comorbidades': aluno.comorbidades or '',
            'nome_responsavel': aluno.nome_responsavel or '',
            'telefone_responsavel': aluno.telefone_responsavel or '',
            'ativo': aluno.ativo,
        })

    # Dicionário JSON completo para os modais de edição e visualização de ficha
    alunos_map = {}
    for a in alunos_list:
        alunos_map[str(a['id'])] = {
            'id': a['id'],
            'nome': a['nome'],
            'turma_id': a['turma'].id if a['turma'] else None,
            'turma_nome': a['turma'].nome if a['turma'] else 'Sem Sala',
            'turno': a['turno'],
            'turno_raw': a['turno_raw'],
            'data_entrada': a['data_entrada'].strftime('%Y-%m-%d') if a['data_entrada'] else '',
            'data_entrada_br': a['data_entrada'].strftime('%d/%m/%Y') if a['data_entrada'] else 'Não informada',
            'data_desligamento': a['data_desligamento'].strftime('%Y-%m-%d') if a['data_desligamento'] else '',
            'data_desligamento_br': a['data_desligamento'].strftime('%d/%m/%Y') if a['data_desligamento'] else '',
            'is_desligamento_futuro': a['is_desligamento_futuro'],
            'has_acompanhamento': a['has_acompanhamento'],
            'acompanhamento_obs': a['acompanhamento_obs'] or '',
            'acompanhamento_dias': a['acompanhamento_dias'] or '',
            'alergias': a['alergias'] or '',
            'restricoes_alimentares': a['restricoes_alimentares'] or '',
            'comorbidades': a['comorbidades'] or '',
            'nome_responsavel': a['nome_responsavel'] or '',
            'telefone_responsavel': a['telefone_responsavel'] or '',
            'ativo': a['ativo'],
        }

    context = {
        'today': today.isoformat(),
        'alunos': alunos_list,
        'alunos_json': json.dumps(alunos_map),
        'total_count': len(alunos_list),
        'turmas': turmas_qs,
        'search': search,
        'classroom_filter': classroom_filter,
        'shift_filter': shift_filter,
        'status_filter': status_filter,
        'dias_semana': [
            ('seg', 'Segunda'),
            ('ter', 'Terça'),
            ('qua', 'Quarta'),
            ('qui', 'Quinta'),
            ('sex', 'Sexta'),
        ],
        'active_tab': 'students',
        'active_module': None,
    }
    return render(request, 'presencas/lista_alunos.html', context)


@login_required
def lista_turmas_view(request):
    """
    Página de Gestão, Criação e Edição de Turmas e Salas da Unidade Escolar.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if request.method == 'POST':
        # Somente Diretores ou Master Admin podem criar/editar turmas
        if not (request.user.is_diretor or request.user.is_master_admin or request.user.is_superuser):
            messages.error(request, "Apenas Diretores e Administradores Master têm permissão para alterar turmas.")
            return redirect('presencas:lista_turmas')

        action = request.POST.get('action')
        turma_id = request.POST.get('turma_id')

        if action in ['create', 'update']:
            nome = request.POST.get('nome', '').strip()
            faixa_etaria = request.POST.get('faixa_etaria', '').strip()
            ativo = request.POST.get('ativo') == 'on'
            professores_ids = request.POST.getlist('professores')

            if not nome:
                messages.error(request, "O nome da turma é obrigatório.")
                return redirect('presencas:lista_turmas')

            if action == 'create':
                if Turma.objects.filter(nome__iexact=nome).exists():
                    messages.error(request, f"Já existe uma turma cadastrada com o nome '{nome}'.")
                    return redirect('presencas:lista_turmas')

                turma = Turma.objects.create(
                    nome=nome,
                    faixa_etaria=faixa_etaria,
                    ativo=ativo
                )
                if professores_ids:
                    turma.professores.set(professores_ids)
                messages.success(request, f"Turma '{turma.nome}' cadastrada com sucesso!")

            elif action == 'update':
                turma = get_object_or_404(Turma, id=turma_id)
                if Turma.objects.filter(nome__iexact=nome).exclude(id=turma.id).exists():
                    messages.error(request, f"Já existe outra turma com o nome '{nome}'.")
                    return redirect('presencas:lista_turmas')

                turma.nome = nome
                turma.faixa_etaria = faixa_etaria
                turma.ativo = ativo
                turma.save()
                turma.professores.set(professores_ids)
                messages.success(request, f"Turma '{turma.nome}' atualizada com sucesso!")

        elif action == 'toggle_active':
            turma = get_object_or_404(Turma, id=turma_id)
            turma.ativo = not turma.ativo
            turma.save()
            status_txt = "ativada" if turma.ativo else "desativada"
            messages.success(request, f"Turma '{turma.nome}' {status_txt} com sucesso!")

        return redirect('presencas:lista_turmas')

    turmas = Turma.objects.prefetch_related('professores', 'alunos').order_by('nome')
    professores_disponiveis = User.objects.filter(is_active=True).order_by('first_name', 'username')

    context = {
        'turmas': turmas,
        'professores_disponiveis': professores_disponiveis,
        'active_tab': 'classrooms',
        'active_module': None,
    }
    return render(request, 'presencas/lista_turmas.html', context)




@login_required
def caderno_seami_view(request, aba='faltas'):
    """
    Módulo II: Caderno SEAMI (/caderno-seami/<aba>/)
    Gerenciamento de Faltas, Atestados, Atrasos, Saídas Antecipadas e Amamentação.
    """
    today = timezone.localdate()
    valid_abas = ['faltas', 'atestados', 'atrasos', 'saidas', 'amamentacao']
    if aba not in valid_abas:
        aba = 'faltas'

    # Mapeamento do tipo de ocorrência no banco
    tipo_map = {
        'faltas': TipoOcorrencia.FALTA,
        'atestados': TipoOcorrencia.ATESTADO,
        'atrasos': TipoOcorrencia.ATRASO,
        'saidas': TipoOcorrencia.SAIDA,
        'amamentacao': TipoOcorrencia.AMAMENTACAO,
    }
    tipo_atual = tipo_map[aba]

    # Processamento de Formulário (POST: Criar / Editar / Excluir)
    if request.method == 'POST':
        action = request.POST.get('action')
        ocorrencia_id = request.POST.get('ocorrencia_id')

        if action == 'delete' and ocorrencia_id:
            if aba == 'amamentacao':
                ocorrencia = get_object_or_404(RegistroAmamentacao, id=ocorrencia_id)
            else:
                ocorrencia = get_object_or_404(OcorrenciaCaderno, id=ocorrencia_id)
            ocorrencia.delete()
            return redirect(request.get_full_path())

        elif action in ['create_historico_amamentacao', 'update_historico_amamentacao']:
            mes_ano = request.POST.get('mes-ano')
            quantidade_str = request.POST.get('quantidade', '0').strip()
            quantidade = int(quantidade_str) if quantidade_str.isdigit() else 0
            observacao = request.POST.get('observacao', '').strip()

            if mes_ano:
                try:
                    data = datetime.strptime(f"{mes_ano}-01", "%Y-%m-%d").date()
                except ValueError:
                    data = today
            else:
                data = today

            if not observacao:
                observacao = f"Quantitativo Total de Amamentações do Mês {data.strftime('%m/%Y')} (Histórico)"

            if action == 'create_historico_amamentacao':
                RegistroAmamentacao.objects.create(
                    data=data,
                    quantidade=quantidade,
                    ano=data.year,
                    mes=data.month,
                    observacao=observacao,
                    registrado_por=request.user
                )
            elif action == 'update_historico_amamentacao' and ocorrencia_id:
                reg = get_object_or_404(RegistroAmamentacao, id=ocorrencia_id)
                reg.data = data
                reg.ano = data.year
                reg.mes = data.month
                reg.quantidade = quantidade
                reg.observacao = observacao
                reg.save()

            return redirect(request.get_full_path())

        elif action in ['create', 'update']:
            tipo_form = request.POST.get('tipo', tipo_atual)

            # Se for registro da Sala de Amamentação, salva na model RegistroAmamentacao
            if aba == 'amamentacao' or tipo_form == 'amamentacao':
                data_str = request.POST.get('data')
                data = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else today
                quantidade_str = request.POST.get('quantidade', '1').strip()
                quantidade = int(quantidade_str) if quantidade_str.isdigit() else 1
                observacao = request.POST.get('observacao', '').strip()
                documento = request.FILES.get('documento')

                if action == 'create':
                    RegistroAmamentacao.objects.create(
                        data=data,
                        quantidade=quantidade,
                        ano=data.year,
                        mes=data.month,
                        observacao=observacao,
                        anexo=documento,
                        attachment_name=documento.name if documento else '',
                        attachment_type=documento.content_type if documento and hasattr(documento, 'content_type') else '',
                        registrado_por=request.user
                    )
                elif action == 'update' and ocorrencia_id:
                    reg = get_object_or_404(RegistroAmamentacao, id=ocorrencia_id)
                    reg.data = data
                    reg.ano = data.year
                    reg.mes = data.month
                    reg.quantidade = quantidade
                    reg.observacao = observacao
                    if documento:
                        reg.anexo = documento
                        reg.attachment_name = documento.name
                        reg.attachment_type = documento.content_type if hasattr(documento, 'content_type') else ''
                    reg.save()

                return redirect(request.get_full_path())

            # Demais ocorrências do Caderno (Faltas, Atestados, Atrasos, Saídas) em OcorrenciaCaderno
            if tipo_form not in [c[0] for c in TipoOcorrencia.choices]:
                tipo_form = tipo_atual

            aluno_id = request.POST.get('aluno')
            turma_id = request.POST.get('turma')
            data_str = request.POST.get('data')
            data_fim_str = request.POST.get('data_fim')
            horario_str = request.POST.get('horario')
            horario_retorno_str = request.POST.get('horario_retorno')
            retorna = request.POST.get('retorna') in ['on', 'sim', 'true', 'True']
            justificado = request.POST.get('justificado') in ['on', 'sim', 'true', 'True']
            avisado_pais = request.POST.get('avisado_pais') in ['on', 'sim', 'true', 'True']
            cid = request.POST.get('cid', '').strip()
            motivo = request.POST.get('motivo', '').strip()
            quantidade = request.POST.get('quantidade', '').strip()
            observacao = request.POST.get('observacao', '').strip()
            documento = request.FILES.get('documento')

            resp_fam = request.POST.get('responsavel_familiar', '').strip()
            resp_staff = request.POST.get('responsavel_staff', '').strip()
            if resp_fam or resp_staff:
                extras = []
                if resp_fam:
                    extras.append(f"Resp. Familiar: {resp_fam}")
                if resp_staff:
                    extras.append(f"Acompanhante: {resp_staff}")
                extra_txt = " | ".join(extras)
                if motivo:
                    motivo = f"{motivo} ({extra_txt})"
                else:
                    motivo = extra_txt

            data = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else today
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

            dias_concedidos_str = request.POST.get('dias_concedidos', '').strip()
            if dias_concedidos_str and data and not data_fim:
                try:
                    dias_val = int(dias_concedidos_str)
                    if dias_val > 1:
                        data_fim = data + timedelta(days=dias_val - 1)
                except ValueError:
                    pass

            horario = None
            if horario_str:
                try:
                    horario = datetime.strptime(horario_str, '%H:%M').time()
                except ValueError:
                    pass

            horario_retorno = None
            if horario_retorno_str and retorna:
                try:
                    horario_retorno = datetime.strptime(horario_retorno_str, '%H:%M').time()
                except ValueError:
                    pass

            aluno = Aluno.objects.filter(id=aluno_id).first() if aluno_id else None
            turma = aluno.turma if aluno else (Turma.objects.filter(id=turma_id).first() if turma_id else None)

            if action == 'create':
                OcorrenciaCaderno.objects.create(
                    tipo=tipo_form,
                    aluno=aluno,
                    turma=turma,
                    data=data,
                    data_fim=data_fim,
                    horario=horario,
                    horario_retorno=horario_retorno,
                    retorna=retorna,
                    justificado=justificado,
                    avisado_pais=avisado_pais,
                    cid=cid,
                    motivo=motivo,
                    quantidade=quantidade,
                    observacao=observacao,
                    documento=documento,
                    registrado_por=request.user
                )
            elif action == 'update' and ocorrencia_id:
                oc = get_object_or_404(OcorrenciaCaderno, id=ocorrencia_id)
                oc.tipo = tipo_form
                oc.aluno = aluno
                oc.turma = turma
                oc.data = data
                oc.data_fim = data_fim
                oc.horario = horario
                oc.horario_retorno = horario_retorno
                oc.retorna = retorna
                oc.justificado = justificado
                oc.avisado_pais = avisado_pais
                oc.cid = cid
                oc.motivo = motivo
                oc.quantidade = quantidade
                oc.observacao = observacao
                if documento:
                    oc.documento = documento
                oc.save()

            return redirect(request.get_full_path())

    # Filtros GET
    search = request.GET.get('q', '').strip()
    classroom_filter = request.GET.get('classroom', '').strip()

    turmas_qs = Turma.objects.filter(ativo=True).order_by('nome')
    alunos_qs = Aluno.objects.filter(ativo=True).select_related('turma').order_by('nome')

    # Paleta de Cores das Turmas
    cores_salas = {
        'amizade': {'bg': '#f5f3ff', 'color': '#7c3aed', 'border': '#ddd6fe', 'emoji': '🎨'},
        'união': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'uniao': {'bg': '#fffbeb', 'color': '#d97706', 'border': '#fde68a', 'emoji': '🤝'},
        'felicidade': {'bg': '#fdf2f8', 'color': '#db2777', 'border': '#fbcfe8', 'emoji': '✨'},
        'carinho': {'bg': '#ecfdf5', 'color': '#059669', 'border': '#a7f3d0', 'emoji': '🧸'},
        'alegria': {'bg': '#eff6ff', 'color': '#2563eb', 'border': '#bfdbfe', 'emoji': '👶'},
    }

    # Títulos e Metadados da Aba
    tab_info = {
        'faltas': {'title': 'Faltas Declaradas', 'subtitle': 'Registro de faltas pontuais ou prolongadas, justificativas e atestados.', 'icon': 'calendar-x', 'color': 'var(--color-faltas)'},
        'atestados': {'title': 'Atestados Médicos', 'subtitle': 'Controle de atestados com CID, períodos de afastamento e anexos.', 'icon': 'activity', 'color': 'var(--color-atestados)'},
        'atrasos': {'title': 'Atrasos de Entrada', 'subtitle': 'Registro de tolerância excedida, horários e motivos declarados.', 'icon': 'clock', 'color': 'var(--color-atrasos)'},
        'saidas': {'title': 'Saídas Antecipadas', 'subtitle': 'Controle de saídas precoces e previsão de retorno no mesmo dia.', 'icon': 'log-out', 'color': 'var(--color-saidas)'},
        'amamentacao': {'title': 'Sala de Amamentação', 'subtitle': 'Registro de sessões, atendimento a lactantes e observações.', 'icon': 'heart', 'color': 'var(--color-amamentacao)'},
    }

    ocorrencias_list = []
    historico_amamentacao = []
    chart_labels = []
    chart_data = []
    meses_consolidado_json = []

    # Se a aba for AMAMENTAÇÃO: busca diretamente da model RegistroAmamentacao
    if aba == 'amamentacao':
        amamentacao_qs = RegistroAmamentacao.objects.all().select_related('registrado_por')
        if search:
            amamentacao_qs = amamentacao_qs.filter(
                Q(observacao__icontains=search) |
                Q(attachment_name__icontains=search)
            )
        amamentacao_qs = amamentacao_qs.order_by('-data')

        for item in amamentacao_qs:
            ocorrencias_list.append({
                'obj': item,
                'id': item.id,
                'aluno': None,
                'turma': None,
                'turma_style': {'bg': '#fdf2f8', 'color': '#db2777', 'border': '#fbcfe8', 'emoji': '🤱'},
                'data': item.data,
                'data_fim': None,
                'periodo': item.data.strftime('%d/%m/%Y'),
                'horario': '',
                'horario_retorno': '',
                'retorna': False,
                'justificado': False,
                'avisado_pais': False,
                'cid': '',
                'motivo': '',
                'quantidade': item.quantidade,
                'observacao': item.observacao,
                'documento': item.anexo,
                'attachment_name': item.attachment_name,
                'registrado_por': item.registrado_por,
                'criado_em': item.criado_em,
            })

        # Agrupamento Mensal para Série Histórica
        mensais_qs = (
            RegistroAmamentacao.objects.values('ano', 'mes')
            .annotate(
                total_quantity=Sum('quantidade'),
                dias_count=Count('id')
            )
            .order_by('-ano', '-mes')
        )

        historico_amamentacao = [
            {
                'month_key': f"{m['ano']:04d}-{m['mes']:02d}",
                'month_label': f"{m['mes']:02d}/{m['ano']}",
                'total_quantity': m['total_quantity'] or 0,
                'entries_count': m['dias_count'],
                'is_daily_sum': True,
                'observacao': f"Somatório de {m['dias_count']} registro(s) no mês",
                'id': None
            }
            for m in mensais_qs
        ]

        meses_pdf_data = sorted(historico_amamentacao, key=lambda x: x['month_key'])
        meses_consolidado_json = [
            {
                'month_key': m['month_key'],
                'month_label': m['month_label'],
                'total_quantity': m['total_quantity'],
                'is_daily_sum': m['is_daily_sum'],
                'observacao': m['observacao'],
            }
            for m in meses_pdf_data
        ]
        chart_labels = [m['month_label'] for m in meses_pdf_data]
        chart_data = [m['total_quantity'] for m in meses_pdf_data]

    else:
        # Faltas, Atestados, Atrasos e Saídas buscam da model OcorrenciaCaderno
        ocorrencias_qs = OcorrenciaCaderno.objects.filter(tipo=tipo_atual).select_related('aluno', 'turma', 'registrado_por')

        if classroom_filter:
            ocorrencias_qs = ocorrencias_qs.filter(
                Q(turma__nome__iexact=classroom_filter) | Q(turma_id=classroom_filter if classroom_filter.isdigit() else None)
            )

        if search:
            ocorrencias_qs = ocorrencias_qs.filter(
                Q(aluno__nome__icontains=search) |
                Q(motivo__icontains=search) |
                Q(cid__icontains=search) |
                Q(observacao__icontains=search)
            )

        for item in ocorrencias_qs.order_by('-data'):
            nome_sala = item.turma.nome.lower().strip() if item.turma else ''
            turma_style = cores_salas.get(nome_sala, {'bg': '#f1f5f9', 'color': '#475569', 'border': '#cbd5e1', 'emoji': '🏫'})
            ocorrencias_list.append({
                'obj': item,
                'id': item.id,
                'aluno': item.aluno,
                'turma': item.turma,
                'turma_style': turma_style,
                'data': item.data,
                'data_fim': item.data_fim,
                'periodo': item.periodo_formatado,
                'horario': item.horario.strftime('%H:%M') if item.horario else '',
                'horario_retorno': item.horario_retorno.strftime('%H:%M') if item.horario_retorno else '',
                'retorna': item.retorna,
                'justificado': item.justificado,
                'avisado_pais': item.avisado_pais,
                'cid': item.cid,
                'motivo': item.motivo,
                'quantidade': item.quantidade,
                'observacao': item.observacao,
                'documento': item.documento,
                'attachment_name': item.attachment_name,
                'registrado_por': item.registrado_por,
                'criado_em': item.criado_em,
            })

    context = {
        'today': today.isoformat(),
        'active_tab_nav': aba,
        'tab_info': tab_info.get(aba, tab_info['faltas']),
        'ocorrencias': ocorrencias_list,
        'total_count': len(ocorrencias_list),
        'turmas': turmas_qs,
        'alunos': alunos_qs,
        'search': search,
        'classroom_filter': classroom_filter,
        'active_tab': 'seami_control',
        'active_module': aba,
        'historico_amamentacao': historico_amamentacao,
        'meses_consolidado_json': json.dumps(meses_consolidado_json),
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'presencas/caderno_seami.html', context)

