import csv
import json
import io
from datetime import datetime, date
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from presencas.models import (
    Turma, Aluno, RegistroPresenca, StatusPresenca,
    DiarioDeClasse, OcorrenciaCaderno, TipoOcorrencia, TurnoAluno
)

User = get_user_model()


def parse_date_flexible(val):
    """Converte strings de data nos formatos comuns para date."""
    if not val:
        return None
    if isinstance(val, date):
        return val
    val = str(val).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    return None


def parse_bool(val):
    """Converte valores textuais ou booleanos para bool."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    val = str(val).strip().lower()
    return val in ['sim', 'true', '1', 'yes', 't', 's']


def load_file_content(uploaded_file):
    """
    Decodifica o arquivo enviado para texto ou JSON.
    Retorna (is_json, data_rows_or_json_list).
    """
    raw = uploaded_file.read()
    
    # Tenta decodificar com utf-8-sig (BOM) ou utf-8 ou latin-1
    for enc in ['utf-8-sig', 'utf-8', 'latin-1']:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('utf-8', errors='ignore')

    # Verifica se é JSON
    stripped = text.strip()
    if stripped.startswith('[') and stripped.endswith(']'):
        try:
            data = json.loads(stripped)
            return True, data
        except json.JSONDecodeError:
            pass

    # Processa como CSV
    sample = text[:2048]
    delimiter = ';' if ';' in sample else ','
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    
    # Normaliza chaves do DictReader (remove espaços)
    rows = []
    for r in reader:
        cleaned_row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k}
        rows.append(cleaned_row)
    return False, rows


def import_turmas(rows, user=None):
    created, updated = 0, 0
    with transaction.atomic():
        for r in rows:
            nome = r.get('Nome da Turma') or r.get('nome') or r.get('Nome')
            if not nome:
                continue
            # Remove sufixos como " (2026)" se presentes no nome
            if ' (' in nome and nome.endswith(')'):
                nome_limpo = nome.split(' (')[0].strip()
            else:
                nome_limpo = nome.strip()

            faixa = r.get('Faixa Etária') or r.get('faixa_etaria') or ''
            ativo = parse_bool(r.get('Status Ativo', r.get('ativo', True)))

            turma, was_created = Turma.objects.get_or_create(
                nome=nome_limpo,
                defaults={
                    'faixa_etaria': faixa,
                    'ativo': ativo
                }
            )
            if was_created:
                created += 1
            else:
                turma.faixa_etaria = faixa or turma.faixa_etaria
                turma.ativo = ativo
                turma.save()
                updated += 1
    return created, updated


def import_alunos(rows, user=None):
    created, updated = 0, 0
    with transaction.atomic():
        for r in rows:
            nome = r.get('Nome da Criança') or r.get('nome') or r.get('Nome')
            if not nome:
                continue

            turma = None
            turma_id = r.get('Turma ID') or r.get('turma_id')
            if turma_id and str(turma_id).isdigit():
                turma = Turma.objects.filter(id=int(turma_id)).first()

            if not turma:
                turma_name = r.get('Turma / Sala') or r.get('turma') or r.get('Turma') or 'Geral'
                if ' (' in turma_name and turma_name.endswith(')'):
                    turma_name = turma_name.split(' (')[0].strip()
                turma, _ = Turma.objects.get_or_create(nome=turma_name.strip())

            turno_str = (r.get('Turno') or r.get('turno') or 'integral').lower()
            turno = TurnoAluno.INTEGRAL
            if 'matutino' in turno_str:
                turno = TurnoAluno.MATUTINO
            elif 'vespertino' in turno_str:
                turno = TurnoAluno.VESPERTINO

            nasc = parse_date_flexible(r.get('Data de Nascimento') or r.get('data_nascimento'))
            entrada = parse_date_flexible(r.get('Data de Entrada') or r.get('data_entrada'))
            deslig = parse_date_flexible(r.get('Data de Desligamento') or r.get('data_desligamento'))
            
            ativo = parse_bool(r.get('Status Ativo', r.get('ativo', True)))
            has_acomp = parse_bool(r.get('Acompanhamento Especial', r.get('has_acompanhamento', False)))
            acomp_obs = r.get('Observações Acompanhamento') or r.get('acompanhamento_obs') or ''
            acomp_dias = r.get('Dias de Acompanhamento') or r.get('acompanhamento_dias') or ''
            resp = r.get('Nome do Responsável') or r.get('nome_responsavel') or ''
            tel = r.get('Telefone do Responsável') or r.get('telefone_responsavel') or ''

            aluno_id = r.get('ID') or r.get('id')
            aluno = None
            if aluno_id and str(aluno_id).isdigit():
                aluno = Aluno.objects.filter(id=int(aluno_id)).first()

            if not aluno:
                aluno, was_created = Aluno.objects.get_or_create(
                    nome=nome.strip(),
                    turma=turma,
                    defaults={
                        'turno': turno,
                        'data_nascimento': nasc,
                        'data_entrada': entrada or timezone.localdate(),
                        'data_desligamento': deslig,
                        'ativo': ativo,
                        'has_acompanhamento': has_acomp,
                        'acompanhamento_obs': acomp_obs,
                        'acompanhamento_dias': acomp_dias,
                        'nome_responsavel': resp,
                        'telefone_responsavel': tel,
                    }
                )
                if was_created:
                    created += 1
                else:
                    aluno.turma = turma
                    aluno.turno = turno
                    if nasc: aluno.data_nascimento = nasc
                    if entrada: aluno.data_entrada = entrada
                    aluno.data_desligamento = deslig
                    aluno.ativo = ativo
                    aluno.has_acompanhamento = has_acomp
                    aluno.acompanhamento_obs = acomp_obs
                    aluno.acompanhamento_dias = acomp_dias
                    if resp: aluno.nome_responsavel = resp
                    if tel: aluno.telefone_responsavel = tel
                    aluno.save()
                    updated += 1
            else:
                aluno.nome = nome.strip()
                aluno.turma = turma
                aluno.turno = turno
                if nasc: aluno.data_nascimento = nasc
                if entrada: aluno.data_entrada = entrada
                aluno.data_desligamento = deslig
                aluno.ativo = ativo
                aluno.has_acompanhamento = has_acomp
                aluno.acompanhamento_obs = acomp_obs
                aluno.acompanhamento_dias = acomp_dias
                if resp: aluno.nome_responsavel = resp
                if tel: aluno.telefone_responsavel = tel
                aluno.save()
                updated += 1
    return created, updated


def import_presencas(rows, user=None):
    created, updated = 0, 0
    status_map = {
        'presente': StatusPresenca.PRESENTE,
        'falta': StatusPresenca.AUSENTE,
        'ausente': StatusPresenca.AUSENTE,
        'falta justificada': StatusPresenca.JUSTIFICADO,
        'justificado': StatusPresenca.JUSTIFICADO,
        'recesso': StatusPresenca.RECESSO,
        'feriado': StatusPresenca.FERIADO,
    }

    with transaction.atomic():
        for r in rows:
            data_val = parse_date_flexible(r.get('Data') or r.get('data'))
            if not data_val:
                continue

            aluno = None
            aluno_id = r.get('Aluno ID') or r.get('aluno_id')
            if aluno_id and str(aluno_id).isdigit():
                aluno = Aluno.objects.filter(id=int(aluno_id)).first()

            aluno_nome = r.get('Aluno') or r.get('aluno')
            if not aluno and aluno_nome:
                aluno = Aluno.objects.filter(nome__iexact=aluno_nome.strip()).first()

            if not aluno and aluno_nome:
                turma_nome = r.get('Turma') or r.get('turma')
                turma, _ = Turma.objects.get_or_create(nome=(turma_nome or 'Geral').strip())
                aluno = Aluno.objects.create(nome=aluno_nome.strip(), turma=turma)

            if not aluno:
                continue

            raw_status = str(r.get('Status de Presença') or r.get('status') or 'PRESENTE').lower().strip()
            status = StatusPresenca.PRESENTE
            for k, v in status_map.items():
                if k in raw_status:
                    status = v
                    break

            obs = r.get('Observação') or r.get('observacao') or ''

            reg = RegistroPresenca.objects.filter(aluno=aluno, data=data_val).first()
            if not reg:
                RegistroPresenca.objects.create(
                    aluno=aluno,
                    data=data_val,
                    turma=aluno.turma,
                    status=status,
                    observacao=obs,
                    registrado_por=user,
                )
                created += 1
            else:
                reg.status = status
                if obs: reg.observacao = obs
                reg.save()
                updated += 1
    return created, updated



def import_ocorrencias(rows, user=None):
    created, updated = 0, 0
    tipo_map = {
        'falta': TipoOcorrencia.FALTA,
        'atestado': TipoOcorrencia.ATESTADO,
        'atraso': TipoOcorrencia.ATRASO,
        'saída': TipoOcorrencia.SAIDA,
        'saida': TipoOcorrencia.SAIDA,
        'amamentação': TipoOcorrencia.AMAMENTACAO,
        'amamentacao': TipoOcorrencia.AMAMENTACAO,
    }

    with transaction.atomic():
        for r in rows:
            tipo_raw = str(
                r.get('tipo_raw') or r.get('tipo') or r.get('Tipo de Ocorrência') or r.get('Tipo') or 'falta'
            ).lower().strip()
            tipo = TipoOcorrencia.FALTA
            for k, v in tipo_map.items():
                if k in tipo_raw:
                    tipo = v
                    break

            data_val = parse_date_flexible(
                r.get('data_inicio') or r.get('data') or r.get('Data Início') or r.get('Data Inicio') or r.get('Data')
            )
            if not data_val:
                continue

            aluno_nome = r.get('aluno') or r.get('Aluno')
            aluno_id = r.get('aluno_id') or r.get('Aluno ID')
            aluno = None
            if aluno_id and str(aluno_id).isdigit():
                aluno = Aluno.objects.filter(id=int(aluno_id)).first()
            if not aluno and aluno_nome and str(aluno_nome).strip() != "Amamentação Geral":
                aluno = Aluno.objects.filter(nome__iexact=str(aluno_nome).strip()).first()

            turma = None
            turma_id = r.get('turma_id') or r.get('Turma ID')
            if turma_id and str(turma_id).isdigit():
                turma = Turma.objects.filter(id=int(turma_id)).first()
            if not turma and aluno:
                turma = aluno.turma
            if not turma:
                turma_nome = r.get('turma') or r.get('Turma')
                if turma_nome:
                    turma = Turma.objects.filter(nome__iexact=str(turma_nome).strip()).first()

            data_fim = parse_date_flexible(r.get('data_fim') or r.get('Data Fim')) or data_val
            justificado = parse_bool(r.get('justificado', r.get('Justificado', False)))
            avisado_pais = parse_bool(r.get('avisado_pais', r.get('Avisado Pais', r.get('Avisado aos Pais', False))))
            cid = r.get('cid') or r.get('CID') or ''
            motivo = r.get('motivo') or r.get('Motivo') or ''
            obs = r.get('observacao') or r.get('Observação') or r.get('Observacao') or ''
            horario_val = r.get('horario') or r.get('Horário') or r.get('Horario') or ''
            horario_retorno_val = r.get('horario_retorno') or r.get('Retorno') or r.get('Horário Retorno') or ''
            qtd_val = r.get('quantidade') or r.get('Quantidade') or 1

            # Converte horario se for formato válido HH:MM ou HH:MM:SS
            h_obj = None
            if horario_val and ':' in str(horario_val):
                try:
                    parts = str(horario_val).strip().split(':')
                    h_obj = datetime.strptime(f"{int(parts[0]):02d}:{int(parts[1]):02d}", "%H:%M").time()
                except Exception:
                    h_obj = None

            hr_obj = None
            if horario_retorno_val and ':' in str(horario_retorno_val):
                try:
                    parts = str(horario_retorno_val).strip().split(':')
                    hr_obj = datetime.strptime(f"{int(parts[0]):02d}:{int(parts[1]):02d}", "%H:%M").time()
                except Exception:
                    hr_obj = None

            existing = None
            row_id = r.get('id') or r.get('ID')
            if row_id and str(row_id).isdigit():
                existing = OcorrenciaCaderno.objects.filter(id=int(row_id)).first()

            if not existing:
                lookup = OcorrenciaCaderno.objects.filter(
                    tipo=tipo,
                    aluno=aluno,
                    data=data_val,
                )
                if motivo:
                    lookup = lookup.filter(motivo=motivo)
                if h_obj:
                    lookup = lookup.filter(horario=h_obj)
                existing = lookup.first()

            if not existing:
                OcorrenciaCaderno.objects.create(
                    tipo=tipo,
                    aluno=aluno,
                    turma=turma,
                    data=data_val,
                    data_fim=data_fim,
                    justificado=justificado,
                    avisado_pais=avisado_pais,
                    cid=cid,
                    motivo=motivo,
                    observacao=obs,
                    horario=h_obj,
                    horario_retorno=hr_obj,
                    quantidade=int(qtd_val) if str(qtd_val).isdigit() else 1,
                    registrado_por=user,
                )
                created += 1
            else:
                existing.turma = turma or existing.turma
                existing.data_fim = data_fim
                existing.justificado = justificado
                existing.avisado_pais = avisado_pais
                existing.cid = cid
                existing.observacao = obs
                if h_obj: existing.horario = h_obj
                if hr_obj: existing.horario_retorno = hr_obj
                existing.save()
                updated += 1

    return created, updated


def import_amamentacao(rows, user=None):
    """Importa registros de amamentação do Caderno SEAMI."""
    created, updated = 0, 0
    with transaction.atomic():
        for r in rows:
            data_val = parse_date_flexible(r.get('data') or r.get('Data'))
            if not data_val:
                continue

            aluno_nome = r.get('aluno') or r.get('Aluno') or r.get('Nome da Criança')
            aluno_id = r.get('aluno_id') or r.get('Aluno ID')
            aluno = None
            if aluno_id and str(aluno_id).isdigit():
                aluno = Aluno.objects.filter(id=int(aluno_id)).first()
            if not aluno and aluno_nome:
                aluno = Aluno.objects.filter(nome__iexact=str(aluno_nome).strip()).first()

            turma = None
            turma_id = r.get('turma_id') or r.get('Turma ID')
            if turma_id and str(turma_id).isdigit():
                turma = Turma.objects.filter(id=int(turma_id)).first()
            if not turma and aluno:
                turma = aluno.turma
            if not turma:
                turma_nome = r.get('turma') or r.get('Turma')
                if turma_nome:
                    turma = Turma.objects.filter(nome__iexact=str(turma_nome).strip()).first()

            qtd_val = r.get('quantidade') or r.get('Quantidade') or r.get('Qtd Mamadeiras') or 1
            try:
                qtd_int = int(qtd_val)
            except Exception:
                qtd_int = 1

            horario_val = r.get('horario') or r.get('Horário') or r.get('Horario') or ''
            h_obj = None
            if horario_val and ':' in str(horario_val):
                try:
                    parts = str(horario_val).strip().split(':')
                    h_obj = datetime.strptime(f"{int(parts[0]):02d}:{int(parts[1]):02d}", "%H:%M").time()
                except Exception:
                    h_obj = None

            motivo = r.get('motivo') or r.get('Motivo') or 'Mamadeira / Leite Materno'
            obs = r.get('observacao') or r.get('Observação') or r.get('Observacao') or ''

            existing = None
            row_id = r.get('id') or r.get('ID')
            if row_id and str(row_id).isdigit():
                existing = OcorrenciaCaderno.objects.filter(id=int(row_id), tipo=TipoOcorrencia.AMAMENTACAO).first()

            if not existing:
                lookup = OcorrenciaCaderno.objects.filter(
                    tipo=TipoOcorrencia.AMAMENTACAO,
                    aluno=aluno,
                    data=data_val,
                )
                if h_obj:
                    lookup = lookup.filter(horario=h_obj)
                existing = lookup.first()

            if not existing:
                OcorrenciaCaderno.objects.create(
                    tipo=TipoOcorrencia.AMAMENTACAO,
                    aluno=aluno,
                    turma=turma,
                    data=data_val,
                    quantidade=qtd_int,
                    motivo=motivo,
                    observacao=obs,
                    horario=h_obj,
                    registrado_por=user,
                )
                created += 1
            else:
                existing.turma = turma or existing.turma
                existing.quantidade = qtd_int
                existing.motivo = motivo
                existing.observacao = obs
                if h_obj: existing.horario = h_obj
                existing.save()
                updated += 1

    return created, updated


def import_enfermaria(rows, user=None):
    """Importa atendimentos clínicos e prontuários da Enfermaria."""
    from presencas.models import AtendimentoEnfermaria
    created, updated = 0, 0
    with transaction.atomic():
        for r in rows:
            data_val = parse_date_flexible(r.get('data_atendimento') or r.get('Data') or r.get('data'))
            if not data_val:
                continue

            aluno_nome = r.get('aluno_nome') or r.get('Nome da Criança') or r.get('Aluno') or r.get('aluno')
            aluno_id = r.get('aluno_id') or r.get('Aluno ID')
            aluno = None
            if aluno_id and str(aluno_id).isdigit():
                aluno = Aluno.objects.filter(id=int(aluno_id)).first()
            if not aluno and aluno_nome:
                aluno = Aluno.objects.filter(nome__iexact=str(aluno_nome).strip()).first()

            if not aluno:
                continue

            horario_val = r.get('horario') or r.get('Horário') or r.get('Horario') or ''
            h_obj = None
            if horario_val and ':' in str(horario_val):
                try:
                    parts = str(horario_val).strip().split(':')
                    h_obj = datetime.strptime(f"{int(parts[0]):02d}:{int(parts[1]):02d}", "%H:%M").time()
                except Exception:
                    h_obj = timezone.now().time()
            else:
                h_obj = timezone.now().time()

            motivo = r.get('motivo') or r.get('Motivo Principal') or r.get('Motivo') or 'Atendimento Clínico'
            motivo_detalhado = r.get('motivo_detalhado') or r.get('Motivo Detalhado') or ''
            cid = r.get('cid') or r.get('CID') or ''
            obs_med = r.get('observacoes_medicas') or r.get('Observações Médicas / Conduta') or r.get('Observações Médicas') or r.get('Observacao') or ''
            saida_imed = parse_bool(r.get('saida_imediata', r.get('Saída Imediata', False)))
            retornara = parse_bool(r.get('retornara_dia_seguinte', r.get('Retornará no Dia Seguinte', True)))
            data_retorno = parse_date_flexible(r.get('data_retorno_prevista') or r.get('Data Retorno') or r.get('Data Prevista de Retorno'))

            existing = None
            row_id = r.get('id') or r.get('ID')
            if row_id and str(row_id).isdigit():
                existing = AtendimentoEnfermaria.objects.filter(id=int(row_id)).first()

            if not existing:
                lookup = AtendimentoEnfermaria.objects.filter(
                    aluno=aluno,
                    data_atendimento=data_val,
                    motivo=motivo
                )
                if h_obj:
                    lookup = lookup.filter(horario=h_obj)
                existing = lookup.first()

            if not existing:
                AtendimentoEnfermaria.objects.create(
                    aluno=aluno,
                    data_atendimento=data_val,
                    horario=h_obj,
                    motivo=motivo,
                    motivo_detalhado=motivo_detalhado,
                    cid=cid,
                    observacoes_medicas=obs_med,
                    saida_imediata=saida_imed,
                    retornara_dia_seguinte=retornara,
                    data_retorno_prevista=data_retorno,
                    registrado_por=user,
                    ativo=True
                )
                created += 1
            else:
                existing.motivo = motivo
                existing.motivo_detalhado = motivo_detalhado
                existing.cid = cid
                existing.observacoes_medicas = obs_med
                existing.saida_imediata = saided_imed if 'saided_imed' in locals() else saida_imed
                existing.retornara_dia_seguinte = retornara
                existing.data_retorno_prevista = data_retorno
                if h_obj: existing.horario = h_obj
                existing.ativo = True
                existing.save()
                updated += 1

    return created, updated


def process_backup_import(uploaded_file, entity, user=None):
    """
    Controlador central de importação para restauração de backup parcial.
    Ordem sequencial:
    1. turmas
    2. alunos
    3. presencas
    4. ocorrencias
    5. amamentacao
    6. enfermaria
    """
    is_json, rows = load_file_content(uploaded_file)
    if not rows:
        raise ValueError("O arquivo enviado está vazio ou não contém dados válidos no formato CSV/JSON.")

    if entity == 'turmas':
        return import_turmas(rows, user)
    elif entity == 'alunos':
        return import_alunos(rows, user)
    elif entity == 'presencas':
        return import_presencas(rows, user)
    elif entity == 'ocorrencias':
        return import_ocorrencias(rows, user)
    elif entity == 'amamentacao':
        return import_amamentacao(rows, user)
    elif entity == 'enfermaria':
        return import_enfermaria(rows, user)
    else:
        raise ValueError(f"Tipo de entidade desconhecido para importação: '{entity}'.")
