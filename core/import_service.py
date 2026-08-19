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
            ano_str = str(r.get('Ano Letivo') or r.get('ano_letivo') or 2026).strip()
            try:
                ano = int(ano_str)
            except ValueError:
                ano = 2026
            
            ativo = parse_bool(r.get('Status Ativo', r.get('ativo', True)))

            turma, was_created = Turma.objects.get_or_create(
                nome=nome_limpo,
                defaults={
                    'faixa_etaria': faixa,
                    'ano_letivo': ano,
                    'ativo': ativo
                }
            )
            if was_created:
                created += 1
            else:
                turma.faixa_etaria = faixa or turma.faixa_etaria
                turma.ano_letivo = ano
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

            turma_name = r.get('Turma / Sala') or r.get('turma') or r.get('Turma') or 'Geral'
            if ' (' in turma_name and turma_name.endswith(')'):
                turma_name = turma_name.split(' (')[0].strip()

            turma, _ = Turma.objects.get_or_create(nome=turma_name.strip(), defaults={'ano_letivo': 2026})

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
            aluno_nome = r.get('Aluno') or r.get('aluno')
            data_val = parse_date_flexible(r.get('Data') or r.get('data'))
            if not aluno_nome or not data_val:
                continue

            turma_nome = r.get('Turma') or r.get('turma')
            aluno = Aluno.objects.filter(nome__iexact=aluno_nome.strip()).first()
            if not aluno:
                turma, _ = Turma.objects.get_or_create(nome=(turma_nome or 'Geral').strip())
                aluno = Aluno.objects.create(nome=aluno_nome.strip(), turma=turma)

            raw_status = str(r.get('Status de Presença') or r.get('status') or 'PRESENTE').lower().strip()
            status = StatusPresenca.PRESENTE
            for k, v in status_map.items():
                if k in raw_status:
                    status = v
                    break

            obs = r.get('Observação') or r.get('observacao') or ''

            reg, was_created = RegistroPresenca.objects.get_or_create(
                aluno=aluno,
                data=data_val,
                defaults={
                    'turma': aluno.turma,
                    'status': status,
                    'observacao': obs,
                    'registrado_por': user,
                }
            )
            if was_created:
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
            tipo_raw = str(r.get('Tipo de Ocorrência') or r.get('tipo') or 'falta').lower()
            tipo = TipoOcorrencia.FALTA
            for k, v in tipo_map.items():
                if k in tipo_raw:
                    tipo = v
                    break

            aluno_nome = r.get('Aluno') or r.get('aluno')
            data_val = parse_date_flexible(r.get('Data Início') or r.get('data') or r.get('Data'))
            if not data_val:
                continue

            aluno = None
            turma = None
            if aluno_nome and aluno_nome != "Amamentação Geral":
                aluno = Aluno.objects.filter(nome__iexact=aluno_nome.strip()).first()
                if aluno:
                    turma = aluno.turma

            data_fim = parse_date_flexible(r.get('Data Fim') or r.get('data_fim'))
            justificado = parse_bool(r.get('Justificado', r.get('justificado', False)))
            cid = r.get('CID') or r.get('cid') or ''
            motivo = r.get('Motivo') or r.get('motivo') or ''
            obs = r.get('Observação') or r.get('observacao') or ''

            ocorrencia, was_created = OcorrenciaCaderno.objects.get_or_create(
                tipo=tipo,
                aluno=aluno,
                data=data_val,
                motivo=motivo,
                defaults={
                    'turma': turma,
                    'data_fim': data_fim,
                    'justificado': justificado,
                    'cid': cid,
                    'observacao': obs,
                    'registrado_por': user,
                }
            )
            if was_created:
                created += 1
            else:
                ocorrencia.data_fim = data_fim
                ocorrencia.justificado = justificado
                ocorrencia.cid = cid
                ocorrencia.observacao = obs
                ocorrencia.save()
                updated += 1
    return created, updated


def process_backup_import(uploaded_file, entity, user=None):
    """
    Controlador central de importação para restauração de backup parcial.
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
    else:
        raise ValueError(f"Tipo de entidade desconhecido para importação: '{entity}'.")
