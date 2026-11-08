from datetime import date
from django.utils import timezone
from django.db.models import Count, Q
from .models import Turma, Aluno, RegistroPresenca, StatusPresenca, DiarioDeClasse


def get_taxa_assiduidade(data_inicio: date, data_fim: date, turma_id: int = None):
    """
    Calcula o percentual e totais de presenças/faltas no intervalo de datas (apenas dias úteis).
    """
    hoje = timezone.localdate()
    filtros = Q(data__gte=data_inicio, data__lte=data_fim, data__week_day__in=[2, 3, 4, 5, 6])
    filtros &= (Q(data__lte=hoje) | Q(diario_classe__isnull=False) | Q(status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL]))
    if turma_id:
        if str(turma_id).isdigit():
            filtros &= Q(turma_id=int(turma_id))
        else:
            t_clean = str(turma_id).replace('Sala', '').replace('sala', '').strip()
            filtros &= (Q(turma__nome__iexact=str(turma_id).strip()) | Q(turma__nome__iexact=t_clean))

    stats = RegistroPresenca.objects.filter(filtros).aggregate(
        total_presentes=Count('id', filter=Q(status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL])),
        total_faltas=Count('id', filter=Q(status=StatusPresenca.AUSENTE)),
        total_justificadas=Count('id', filter=Q(status=StatusPresenca.JUSTIFICADO)),
    )

    presentes = stats['total_presentes'] or 0
    faltas = stats['total_faltas'] or 0
    justificadas = stats['total_justificadas'] or 0
    total = presentes + faltas + justificadas
    taxa = round((presentes / total * 100), 1) if total > 0 else 100.0

    return {
        'taxa_percentual': taxa,
        'total_registros': total,
        'total_presentes': presentes,
        'total_faltas': faltas,
        'total_justificadas': justificadas,
    }


def get_radar_alunos_em_risco(limite_faltas: int = 3):
    """
    Radar de Alerta: Identifica crianças ativas cujos últimos registros são faltas consecutivas (não justificadas).
    """
    alunos_em_risco = []
    alunos_ativos = Aluno.objects.filter(ativo=True).select_related('turma')

    for aluno in alunos_ativos:
        ultimos_status = list(
            aluno.presencas.order_by('-data')
            .values_list('status', flat=True)[:limite_faltas]
        )

        if len(ultimos_status) == limite_faltas and all(s == StatusPresenca.AUSENTE for s in ultimos_status):
            alunos_em_risco.append({
                'aluno': aluno,
                'aluno_id': aluno.id,
                'nome': aluno.nome,
                'turma_nome': aluno.turma.nome,
                'faltas_consecutivas': limite_faltas,
                'telefone_responsavel': aluno.telefone_responsavel,
                'nome_responsavel': aluno.nome_responsavel,
            })

    return alunos_em_risco


def get_novas_matriculas_periodo(data_inicio: date, data_fim: date):
    """
    Retorna a listagem de crianças cuja data de entrada (matrícula) ocorreu no período selecionado.
    """
    return Aluno.objects.filter(
        data_entrada__range=(data_inicio, data_fim)
    ).select_related('turma').order_by('-data_entrada', 'nome')


import os
import json
import calendar
from django.conf import settings


def get_headcount_file_path():
    """Retorna o caminho do arquivo JSON persistido para cache de headcount."""
    base_dir = getattr(settings, 'BASE_DIR', None)
    if base_dir:
        data_dir = os.path.join(base_dir, 'data')
    else:
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'matriculados_headcount.json')


def calcular_e_salvar_matriculados_headcount(year: int = None):
    """
    Calcula e persiste em JSON o total de alunos com matrícula ativa mês a mês para o ano especificado.
    Formato gerado: {"YYYY-MM": total, ...} e metadados detalhados para relatórios PDF/XLSX.
    """
    if year is None:
        year = timezone.localdate().year

    alunos = list(Aluno.objects.all().select_related('turma'))
    headcount_map = {}
    detalhes_map = {}

    for m in range(1, 13):
        last_day = calendar.monthrange(year, m)[1]
        start_m = date(year, m, 1)
        end_m = date(year, m, last_day)
        m_key = f"{year}-{m:02d}"

        active_students = []
        salas_count = {}

        for a in alunos:
            entry = a.data_entrada or date(2000, 1, 1)
            deact = a.data_desligamento
            if entry <= end_m and (deact is None or deact >= start_m):
                active_students.append(a)
                turma_nome = a.turma.nome if a.turma else 'Geral'
                salas_count[turma_nome] = salas_count.get(turma_nome, 0) + 1

        total = len(active_students)
        headcount_map[m_key] = total
        detalhes_map[m_key] = {
            'ano': year,
            'mes': m,
            'mes_extenso': ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'][m - 1],
            'mes_abrev': ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'][m - 1],
            'total_matriculados': total,
            'por_sala': salas_count
        }

    full_payload = {
        'updated_at': timezone.now().isoformat(),
        'year': year,
        'headcount': headcount_map,
        'detalhes': detalhes_map
    }

    file_path = get_headcount_file_path()
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(full_payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Services] Erro ao salvar cache JSON de headcount: {e}")

    return full_payload


def get_matriculados_headcount_json(year: int = None, force_refresh: bool = False):
    """
    Retorna instantaneamente o dicionário { 'YYYY-MM': total } lendo do arquivo JSON cacheado.
    Se não existir ou for forçado, calcula e salva em cache.
    """
    if year is None:
        year = timezone.localdate().year

    file_path = get_headcount_file_path()

    if not force_refresh and os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('year') == year and 'headcount' in data:
                    return data
        except Exception:
            pass

    return calcular_e_salvar_matriculados_headcount(year=year)


def get_historical_frequency_file_path():
    """Retorna o caminho do arquivo JSON persistido para dados históricos de frequência."""
    base_dir = getattr(settings, 'BASE_DIR', None)
    if base_dir:
        data_dir = os.path.join(base_dir, 'data')
    else:
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'historical_frequency.json')


def sync_historical_frequency_from_supabase():
    """
    Sincroniza os registros históricos de 'Frequência vs Matriculados' da tabela settings do Supabase.
    Armazena em JSON local para carregamento instantâneo em relatórios e gráficos.
    """
    import urllib.request
    supabase_url = "https://lmzmxzubwxaplynljcqy.supabase.co"
    supabase_key = "sb_publishable_AqsFvbZgd9D2xdR4VFOwqQ_Dwk_aulu"

    url = f"{supabase_url}/rest/v1/settings?key=eq.historical_data&select=key,value"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 206):
                raw = json.loads(resp.read().decode('utf-8'))
                if raw and len(raw) > 0 and 'value' in raw[0]:
                    hist_list = json.loads(raw[0]['value'])
                    file_path = get_historical_frequency_file_path()
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(hist_list, f, ensure_ascii=False, indent=2)
                    print(f"[Services] {len(hist_list)} registros históricos de frequência sincronizados com sucesso!")
                    return hist_list
    except Exception as e:
        print(f"[Services] Erro ao sincronizar dados históricos do Supabase: {e}")

    return []


def get_historical_frequency_data():
    """
    Retorna a lista completa de registros históricos [{id, month, enrolled, present}, ...]
    consultando diretamente a model HistoricoFrequenciaMensal no banco de dados.
    Caso a tabela esteja vazia ou com menos registros que a série histórica oficial (ex: deploy novo na VPS),
    auto-popula a partir do arquivo JSON oficial local garantindo consistência completa (2019 até 2026).
    """
    from .models import HistoricoFrequenciaMensal
    registros_qs = HistoricoFrequenciaMensal.objects.all().order_by('-ano', '-mes')
    count = registros_qs.count()

    if count < 90:
        file_path = get_historical_frequency_file_path()
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    hist_list = json.load(f)

                for item in hist_list:
                    m_str = item.get('month', '')
                    if m_str and '-' in m_str:
                        parts = m_str.split('-')
                        ano = int(parts[0])
                        mes = int(parts[1])
                        enr = int(item.get('enrolled', 0))
                        pres = int(item.get('present', 0))
                        absent = max(0, enr - pres)
                        taxa = round((pres / enr) * 100, 1) if enr > 0 else 0.0

                        HistoricoFrequenciaMensal.objects.update_or_create(
                            mes_ano=m_str,
                            defaults={
                                'ano': ano,
                                'mes': mes,
                                'matriculados': enr,
                                'presentes_media': pres,
                                'ausentes_media': absent,
                                'taxa_frequencia': taxa,
                                'observacao': f"Série histórica oficial ({m_str})"
                            }
                        )
                registros_qs = HistoricoFrequenciaMensal.objects.all().order_by('-ano', '-mes')
            except Exception as e:
                print(f"[Services] Erro ao carregar/popular dados históricos: {e}")

    return [
        {
            'id': f"hist_{r.id}",
            'month': r.mes_ano,
            'enrolled': r.matriculados,
            'present': r.presentes_media,
            'absences': r.ausentes_media,
            'percentage': r.taxa_frequencia,
            'observacao': r.observacao,
        }
        for r in registros_qs
    ]


def calcular_consolidado_mensal_sistema(ano_inicio: int = 2026, mes_inicio: int = 8, turma_id=None, status_aluno='all'):
    """
    Consolida mês a mês as chamadas do Diário de Classe do sistema a partir de Agosto de 2026 até o presente.
    Calcula:
      - Matriculados: MÁXIMA de alunos matriculados ativos no mês (capacidade de pico diária).
      - Presentes: Média diária de alunos presentes em dias úteis com chamada.
      - Ausentes: Máxima de matriculados - Média de presentes.
      - Taxa de Frequência: (Presentes / Máxima de Matriculados) * 100.
    Retorna a lista de meses calculados e o resumo consolidado do período inteiro preenchido pelo sistema.
    """
    import calendar
    from datetime import date
    from django.utils import timezone
    from django.db.models import Q
    from .models import Aluno, RegistroPresenca, StatusPresenca

    hoje = timezone.localdate()
    ano_atual = hoje.year
    mes_atual = hoje.month

    MONTH_NAMES_EXTENSO = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

    aluno_base = Aluno.objects.all()
    turma_q_aluno = None
    turma_q_reg = None
    if turma_id:
        t_str = str(turma_id).strip()
        if t_str.isdigit():
            turma_q_aluno = Q(turma_id=int(t_str))
            turma_q_reg = Q(turma_id=int(t_str))
        elif t_str:
            t_clean = t_str.replace('Sala', '').replace('sala', '').strip()
            turma_q_aluno = Q(turma__nome__iexact=t_str) | Q(turma__nome__iexact=t_clean)
            turma_q_reg = Q(turma__nome__iexact=t_str) | Q(turma__nome__iexact=t_clean)
    if turma_q_aluno is not None:
        aluno_base = aluno_base.filter(turma_q_aluno)
    if status_aluno == 'ativos':
        aluno_base = aluno_base.filter(ativo=True)
    elif status_aluno == 'inativos':
        aluno_base = aluno_base.filter(ativo=False)

    meses_calculados = []
    total_presentes_acumulado = 0
    total_registros_acumulado = 0
    total_dias_letivos_acumulado = 0
    max_matriculados_geral = 0

    for ano in range(ano_inicio, ano_atual + 1):
        m_start = mes_inicio if ano == ano_inicio else 1
        m_end = mes_atual if ano == ano_atual else 12

        for mes in range(m_start, m_end + 1):
            ultimo_dia = calendar.monthrange(ano, mes)[1]
            data_inicio_mes = date(ano, mes, 1)
            data_fim_mes = date(ano, mes, ultimo_dia)
            mes_key = f"{ano}-{mes:02d}"

            # Registros de Presença em dias úteis (Segunda a Sexta), ignorando ausências futuras sem diário lançado
            regs_mes = RegistroPresenca.objects.filter(
                data__gte=data_inicio_mes,
                data__lte=data_fim_mes,
                data__week_day__in=[2, 3, 4, 5, 6]
            ).filter(
                Q(data__lte=hoje) | Q(diario_classe__isnull=False) | Q(status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL])
            )
            if turma_q_reg is not None:
                regs_mes = regs_mes.filter(turma_q_reg)
            if status_aluno == 'ativos':
                regs_mes = regs_mes.filter(aluno__ativo=True)
            elif status_aluno == 'inativos':
                regs_mes = regs_mes.filter(aluno__ativo=False)

            # Dias efetivos com chamada (prioriza dias com diário lançado ou presença registrada)
            datas_chamada_efetiva = set(
                regs_mes.filter(
                    Q(diario_classe__isnull=False) | Q(status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL])
                ).values_list('data', flat=True)
            )
            datas_chamada = datas_chamada_efetiva or set(regs_mes.values_list('data', flat=True))
            dias_com_chamada = len(datas_chamada)
            
            # Se for mês sem chamadas lançadas, ignora para não poluir com 0%
            if dias_com_chamada == 0:
                continue

            # Filtra os registros do mês apenas nos dias que efetivamente tiveram chamada
            regs_mes_validos = regs_mes.filter(data__in=datas_chamada)

            # 1. MÁXIMA de alunos matriculados ativos no mês
            max_matriculados_mes = 0
            dias_para_checar = sorted(list(datas_chamada))

            for d_check in dias_para_checar:
                count_dia = aluno_base.filter(
                    Q(data_entrada__isnull=True) | Q(data_entrada__lte=d_check)
                ).filter(
                    Q(data_desligamento__isnull=True) | Q(data_desligamento__gte=d_check)
                ).count()
                count_chamada_dia = regs_mes_validos.filter(
                    data=d_check,
                    status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL, StatusPresenca.AUSENTE, StatusPresenca.JUSTIFICADO]
                ).count()
                pico_dia = max(count_dia, count_chamada_dia)
                if pico_dia > max_matriculados_mes:
                    max_matriculados_mes = pico_dia

            if max_matriculados_mes == 0:
                max_matriculados_mes = aluno_base.filter(
                    Q(data_entrada__isnull=True) | Q(data_entrada__lte=data_fim_mes)
                ).filter(
                    Q(data_desligamento__isnull=True) | Q(data_desligamento__gte=data_inicio_mes)
                ).count()

            if max_matriculados_mes > max_matriculados_geral:
                max_matriculados_geral = max_matriculados_mes

            # 2. Média de alunos presentes / dia e Taxa de Assiduidade alinhada com o Painel Geral
            if dias_com_chamada > 0:
                pres_count = regs_mes_validos.filter(status__in=[StatusPresenca.PRESENTE, StatusPresenca.PARCIAL]).count()
                falt_count = regs_mes_validos.filter(status__in=[StatusPresenca.AUSENTE, StatusPresenca.JUSTIFICADO]).count()
                tot_count = pres_count + falt_count
                p_media = round(pres_count / dias_com_chamada)
                total_presentes_acumulado += pres_count
                total_registros_acumulado += tot_count
                total_dias_letivos_acumulado += dias_com_chamada
            else:
                pres_count = 0
                tot_count = 0
                p_media = 0

            a_media = max(0, max_matriculados_mes - p_media)
            pct = round((pres_count / tot_count) * 100) if tot_count > 0 else (round((p_media / max_matriculados_mes) * 100) if max_matriculados_mes > 0 else 0)
            m_ext = MONTH_NAMES_EXTENSO[mes] if (0 <= mes < len(MONTH_NAMES_EXTENSO)) else str(mes)

            meses_calculados.append({
                'id': f"sistema_{mes_key}",
                'month': mes_key,
                'month_formatted': f"{m_ext} / {ano}",
                'year': ano,
                'month_num': mes,
                'enrolled': max_matriculados_mes,  # MÁXIMA
                'present': p_media,
                'absences': a_media,
                'percentage': pct,
                'origem': 'sistema',
                'origem_label': 'Diário SEAMI',
                'dias_letivos': dias_com_chamada,
            })

    # Resumo Consolidado Geral do Período do Sistema (Agosto/2026 até Hoje)
    if total_dias_letivos_acumulado > 0:
        media_presentes_geral = round(total_presentes_acumulado / total_dias_letivos_acumulado)
    else:
        media_presentes_geral = 0
    
    media_ausentes_geral = max(0, max_matriculados_geral - media_presentes_geral)
    if total_registros_acumulado > 0:
        taxa_frequencia_geral = round((total_presentes_acumulado / total_registros_acumulado) * 100)
    else:
        taxa_frequencia_geral = round((media_presentes_geral / max_matriculados_geral) * 100) if max_matriculados_geral > 0 else 0

    consolidado_resumo = {
        'matriculados_max': max_matriculados_geral,
        'media_presentes': media_presentes_geral,
        'media_ausentes': media_ausentes_geral,
        'taxa_frequencia': taxa_frequencia_geral,
        'total_dias_letivos': total_dias_letivos_acumulado,
        'total_meses': len(meses_calculados),
    }

    return meses_calculados, consolidado_resumo



def sincronizar_automacoes_enfermaria(atendimento, user=None):
    """
    Sincroniza as ocorrências do Caderno SEAMI e registros de presença vinculados ao atendimento:
    1. Saída Imediata no dia do atendimento -> Registrada como SAÍDA ANTECIPADA (tipo='saida'), NÃO como falta.
       A presença do dia em si não é transformada em falta (a criança esteve presente).
    2. Se retorna amanhã (no dia seguinte) -> Apenas a saída antecipada é registrada.
    3. Se retorna em data posterior -> Além da saída antecipada de hoje, registra ocorrências de FALTA JUSTIFICADA
       (tipo='falta', justificado=True) no Caderno SEAMI para os dias úteis entre amanhã e a véspera do retorno,
       e atualiza/marca a chamada como FALTA JUSTIFICADA (FJ / JUSTIFICADO).
    """
    from datetime import timedelta
    from .models import (
        AtendimentoEnfermaria, OcorrenciaCaderno, TipoOcorrencia,
        RegistroPresenca, StatusPresenca, StatusTurnoPresenca,
        extrair_nome_usuario
    )

    aluno = atendimento.aluno
    data_atendimento = atendimento.data_atendimento
    horario = atendimento.horario
    motivo = atendimento.motivo
    motivo_detalhado = atendimento.motivo_detalhado
    cid = atendimento.cid
    observacoes_medicas = atendimento.observacoes_medicas
    saida_imediata = atendimento.saida_imediata
    retornara_dia_seguinte = atendimento.retornara_dia_seguinte
    data_retorno_prevista = atendimento.data_retorno_prevista
    reg_user = user or atendimento.registrado_por
    registrado_por = reg_user if (reg_user and getattr(reg_user, 'pk', None)) else None
    registrado_por_nome = extrair_nome_usuario(registrado_por)

    # 1. Automação de Saída Antecipada do dia (NÃO gera falta para a data de saída)
    if saida_imediata:
        motivo_saida = f"Atendimento Enfermagem: {motivo}"
        if motivo_detalhado:
            motivo_saida += f" ({motivo_detalhado})"
        if cid:
            motivo_saida += f" [CID: {cid}]"

        oc_saida, created = OcorrenciaCaderno.objects.get_or_create(
            tipo=TipoOcorrencia.SAIDA,
            aluno=aluno,
            data=data_atendimento,
            defaults={
                'turma': aluno.turma,
                'horario': horario,
                'motivo': motivo_saida,
                'justificado': True,
                'retorna': False,
                'cid': cid or '',
                'observacao': observacoes_medicas or '',
                'registrado_por': registrado_por,
                'registrado_por_nome': registrado_por_nome
            }
        )
        if not created:
            oc_saida.horario = horario
            oc_saida.motivo = motivo_saida
            oc_saida.cid = cid or ''
            oc_saida.observacao = observacoes_medicas or ''
            oc_saida.registrado_por = registrado_por
            oc_saida.registrado_por_nome = registrado_por_nome
            oc_saida.save()

    # 2. Automação de Falta Justificada como registro único de período até a data de retorno
    if saida_imediata and not retornara_dia_seguinte and data_retorno_prevista:
        start_date = data_atendimento + timedelta(days=1)
        end_date = data_retorno_prevista - timedelta(days=1)

        if start_date <= end_date:
            motivo_falta = f"Afastamento Médico / Enfermagem: {motivo}"
            if cid:
                motivo_falta += f" (CID: {cid})"

            # Cria um único registro de Falta Justificada com período (início e fim)
            OcorrenciaCaderno.objects.update_or_create(
                tipo=TipoOcorrencia.FALTA,
                aluno=aluno,
                data=start_date,
                defaults={
                    'data_fim': end_date,
                    'turma': aluno.turma,
                    'motivo': motivo_falta,
                    'justificado': True,
                    'cid': cid or '',
                    'observacao': observacoes_medicas or f"Afastamento de Enfermagem com retorno previsto em {data_retorno_prevista.strftime('%d/%m/%Y')}",
                    'registrado_por': registrado_por,
                    'registrado_por_nome': registrado_por_nome
                }
            )
            # A sincronização com RegistroPresenca para todos os dias úteis do período
            # ocorre automaticamente via signal post_save (sincronizar_ocorrencia_com_presenca)


def reverter_automacoes_enfermaria(atendimento):
    """
    Ao excluir ou desativar um atendimento de enfermagem:
    1. Remove a ocorrência de SAÍDA ANTECIPADA gerada para a data do atendimento.
    2. Remove as ocorrências de FALTA JUSTIFICADA geradas para os dias de afastamento subsequentes.
    3. Para cada dia de afastamento, caso o RegistroPresenca tenha sido criado antecipadamente
       sem a chamada oficial do professor (diario_classe is None), remove o RegistroPresenca;
       caso já tenha sido lançado pelo professor, o signal post_delete reverte o status de volta para AUSENTE.
    """
    from datetime import timedelta
    from django.db.models import Q
    from .models import OcorrenciaCaderno, TipoOcorrencia, RegistroPresenca, StatusPresenca

    aluno = atendimento.aluno
    data_atendimento = atendimento.data_atendimento

    # 1. Remove Saída Antecipada gerada pelo atendimento de Enfermagem
    OcorrenciaCaderno.objects.filter(
        aluno=aluno,
        data=data_atendimento,
        tipo=TipoOcorrencia.SAIDA
    ).filter(
        Q(motivo__icontains='Enfermagem') | Q(motivo__icontains='Enfermaria') | Q(motivo__icontains=atendimento.motivo)
    ).delete()

    # 2. Remove Faltas Justificadas geradas nos dias de afastamento subsequentes
    if atendimento.data_retorno_prevista:
        start_date = data_atendimento + timedelta(days=1)
        end_date = atendimento.data_retorno_prevista - timedelta(days=1)
        if start_date <= end_date:
            ocorrs_afastamento = OcorrenciaCaderno.objects.filter(
                aluno=aluno,
                tipo=TipoOcorrencia.FALTA
            ).filter(
                Q(data=start_date) |
                (Q(data__gte=start_date) & Q(data__lte=end_date)) |
                (Q(data__lte=start_date) & Q(data_fim__gte=end_date))
            ).filter(
                Q(motivo__icontains='Enfermagem') | Q(motivo__icontains='Enfermaria') | Q(motivo__icontains='Afastamento')
            )
            for oc in ocorrs_afastamento:
                oc.delete()

            # Limpa registros de presença órfãos criados antecipadamente sem diário de chamada
            RegistroPresenca.objects.filter(
                aluno=aluno,
                data__gte=start_date,
                data__lte=end_date,
                diario_classe__isnull=True,
                status=StatusPresenca.AUSENTE
            ).delete()


def registrar_atendimento_enfermaria(
    aluno,
    data_atendimento,
    horario=None,
    motivo='Atendimento Clínico Geral',
    motivo_detalhado='',
    saida_imediata=False,
    retornara_dia_seguinte=True,
    data_retorno_prevista=None,
    observacoes_medicas='',
    cid='',
    documento_anexo=None,
    registrado_por=None
):
    """
    Registra um atendimento clínico na Enfermagem e dispara as automações:
    1. Cria AtendimentoEnfermaria.
    2. Se saída imediata -> Cria OcorrenciaCaderno (tipo='saida').
    3. Se não retorna amanhã e tem data de retorno -> Cria OcorrenciaCaderno (tipo='falta', justificado=True)
       e RegistroPresenca (status=JUSTIFICADO) para cada dia útil até a véspera da data de retorno.
    """
    from .models import AtendimentoEnfermaria, extrair_nome_usuario

    from datetime import datetime
    if not horario:
        horario = datetime.now().time()

    user_obj = registrado_por if (registrado_por and getattr(registrado_por, 'pk', None)) else None

    atendimento = AtendimentoEnfermaria.objects.create(
        aluno=aluno,
        data_atendimento=data_atendimento,
        horario=horario,
        motivo=motivo,
        motivo_detalhado=motivo_detalhado,
        saida_imediata=saida_imediata,
        retornara_dia_seguinte=retornara_dia_seguinte,
        data_retorno_prevista=data_retorno_prevista if (saida_imediata and not retornara_dia_seguinte) else None,
        observacoes_medicas=observacoes_medicas,
        cid=cid,
        documento_anexo=documento_anexo,
        registrado_por=user_obj,
        ativo=True
    )

    sincronizar_automacoes_enfermaria(atendimento, user=user_obj)
    return atendimento
