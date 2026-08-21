import os
import json
import csv
from datetime import datetime

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from presencas.models import (
    Turma, Aluno, RegistroPresenca, StatusPresenca,
    OcorrenciaCaderno, TipoOcorrencia, AtendimentoEnfermaria
)

User = get_user_model()
os.makedirs('export_data', exist_ok=True)

print("Exportando Turmas...")
turmas = Turma.objects.prefetch_related('professores', 'alunos').order_by('nome')
turmas_json = [
    {
        "id": t.id,
        "nome": t.nome,
        "faixa_etaria": t.faixa_etaria,
        "ativo": t.ativo,
        "total_alunos": t.alunos.count(),
        "professores": [p.get_full_name() or p.username for p in t.professores.all()],
    }
    for t in turmas
]
with open('export_data/1_turmas_seami.json', 'w', encoding='utf-8') as f:
    json.dump(turmas_json, f, indent=2, ensure_ascii=False)

with open('export_data/1_turmas_seami.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(["ID", "Nome da Turma", "Faixa Etária", "Total de Alunos", "Professores Responsáveis", "Status Ativo"])
    for t in turmas:
        profs = ", ".join([p.get_full_name() or p.username for p in t.professores.all()])
        w.writerow([t.id, t.nome, t.faixa_etaria, t.alunos.count(), profs, "Sim" if t.ativo else "Não"])

print("Exportando Alunos...")
alunos = Aluno.objects.select_related('turma').order_by('turma__nome', 'nome')
alunos_json = [
    {
        "id": a.id,
        "nome": a.nome,
        "turma_id": a.turma_id,
        "turma": a.turma.nome if a.turma else "",
        "turno": a.get_turno_display(),
        "data_nascimento": a.data_nascimento.strftime("%d/%m/%Y") if a.data_nascimento else "",
        "data_entrada": a.data_entrada.strftime("%d/%m/%Y") if a.data_entrada else "",
        "data_desligamento": a.data_desligamento.strftime("%d/%m/%Y") if a.data_desligamento else "",
        "ativo": a.ativo,
        "has_acompanhamento": a.has_acompanhamento,
        "acompanhamento_obs": a.acompanhamento_obs,
        "acompanhamento_dias": a.acompanhamento_dias,
        "alergias": a.alergias or "",
        "restricoes_alimentares": a.restricoes_alimentares or "",
        "comorbidades": a.comorbidades or "",
        "nome_responsavel": a.nome_responsavel,
        "telefone_responsavel": a.telefone_responsavel,
    }
    for a in alunos
]
with open('export_data/2_alunos_seami.json', 'w', encoding='utf-8') as f:
    json.dump(alunos_json, f, indent=2, ensure_ascii=False)

with open('export_data/2_alunos_seami.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow([
        "ID", "Nome da Criança", "Turma ID", "Turma / Sala", "Turno", "Data de Nascimento",
        "Data de Entrada", "Data de Desligamento", "Status Ativo", "Acompanhamento Especial",
        "Observações Acompanhamento", "Dias de Acompanhamento", "Alergias", "Restrições Alimentares", "Comorbidades",
        "Nome do Responsável", "Telefone do Responsável"
    ])
    for a in alunos:
        w.writerow([
            a.id, a.nome, a.turma_id or "", a.turma.nome if a.turma else "", a.get_turno_display(),
            a.data_nascimento.strftime("%d/%m/%Y") if a.data_nascimento else "",
            a.data_entrada.strftime("%d/%m/%Y") if a.data_entrada else "",
            a.data_desligamento.strftime("%d/%m/%Y") if a.data_desligamento else "",
            "Sim" if a.ativo else "Não", "Sim" if a.has_acompanhamento else "Não",
            a.acompanhamento_obs, a.acompanhamento_dias, a.alergias or "",
            a.restricoes_alimentares or "", a.comorbidades or "",
            a.nome_responsavel, a.telefone_responsavel
        ])

print("Exportando Presenças...")
presencas = RegistroPresenca.objects.select_related('aluno', 'turma', 'registrado_por').order_by('-data', 'turma__nome', 'aluno__nome')
presencas_json = [
    {
        "id": r.id,
        "data": r.data.strftime("%d/%m/%Y"),
        "turma_id": r.turma_id,
        "turma": r.turma.nome if r.turma else "",
        "aluno_id": r.aluno_id,
        "aluno": r.aluno.nome if r.aluno else "",
        "status": r.get_status_display(),
        "status_key": r.status,
        "status_matutino": r.status_matutino,
        "status_vespertino": r.status_vespertino,
        "observacao": r.observacao,
        "registrado_por": r.registrado_por.get_full_name() or r.registrado_por.username if r.registrado_por else "",
        "criado_em": timezone.localtime(r.criado_em).strftime("%d/%m/%Y %H:%M:%S") if r.criado_em else "",
    }
    for r in presencas
]
with open('export_data/3_registros_presenca_seami.json', 'w', encoding='utf-8') as f:
    json.dump(presencas_json, f, indent=2, ensure_ascii=False)

with open('export_data/3_registros_presenca_seami.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(["ID", "Data", "Turma ID", "Turma", "Aluno ID", "Aluno", "Status de Presença", "Status Matutino", "Status Vespertino", "Observação", "Registrado por", "Criado em"])
    for r in presencas:
        w.writerow([
            r.id, r.data.strftime("%d/%m/%Y"), r.turma_id or "", r.turma.nome if r.turma else "",
            r.aluno_id or "", r.aluno.nome if r.aluno else "", r.get_status_display(),
            r.status_matutino, r.status_vespertino, r.observacao,
            r.registrado_por.get_full_name() or r.registrado_por.username if r.registrado_por else "",
            timezone.localtime(r.criado_em).strftime("%d/%m/%Y %H:%M:%S") if r.criado_em else "",
        ])

print("Exportando Ocorrências...")
ocorrencias = OcorrenciaCaderno.objects.exclude(tipo=TipoOcorrencia.AMAMENTACAO).select_related('aluno', 'turma', 'registrado_por').order_by('-data', '-criado_em')
ocorrencias_json = [
    {
        "id": o.id,
        "tipo": o.get_tipo_display(),
        "tipo_raw": o.tipo,
        "aluno_id": o.aluno_id,
        "aluno": o.aluno.nome if o.aluno else "",
        "turma_id": o.turma_id,
        "turma": o.turma.nome if o.turma else "",
        "data_inicio": o.data.strftime("%d/%m/%Y"),
        "data_fim": o.data_fim.strftime("%d/%m/%Y") if o.data_fim else "",
        "periodo": o.periodo_formatado,
        "horario": str(o.horario) if o.horario else "",
        "horario_retorno": str(o.horario_retorno) if o.horario_retorno else "",
        "justificado": o.justificado,
        "avisado_pais": o.avisado_pais,
        "cid": o.cid,
        "motivo": o.motivo,
        "quantidade": o.quantidade,
        "observacao": o.observacao,
        "registrado_por": o.registrado_por.get_full_name() or o.registrado_por.username if o.registrado_por else "",
    }
    for o in ocorrencias
]
with open('export_data/4_caderno_seami_ocorrencias.json', 'w', encoding='utf-8') as f:
    json.dump(ocorrencias_json, f, indent=2, ensure_ascii=False)

with open('export_data/4_caderno_seami_ocorrencias.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow([
        "ID", "Tipo de Ocorrência", "Aluno ID", "Aluno", "Turma ID", "Turma", "Data Início", "Data Fim",
        "Período Formatado", "Horário", "Retorno", "Justificado", "Avisado Pais", "CID", "Motivo", "Quantidade", "Observação", "Registrado por"
    ])
    for o in ocorrencias:
        w.writerow([
            o.id, o.get_tipo_display(), o.aluno_id or "", o.aluno.nome if o.aluno else "",
            o.turma_id or "", o.turma.nome if o.turma else "", o.data.strftime("%d/%m/%Y"),
            o.data_fim.strftime("%d/%m/%Y") if o.data_fim else "", o.periodo_formatado,
            str(o.horario) if o.horario else "",
            str(o.horario_retorno) if o.horario_retorno else ("Sim" if o.retorna else "Não"),
            "Sim" if o.justificado else "Não", "Sim" if o.avisado_pais else "Não",
            o.cid, o.motivo, o.quantidade, o.observacao,
            o.registrado_por.get_full_name() or o.registrado_por.username if o.registrado_por else "",
        ])

print("Exportando Amamentação...")
amamentacao = OcorrenciaCaderno.objects.filter(tipo=TipoOcorrencia.AMAMENTACAO).select_related('aluno', 'turma', 'registrado_por').order_by('-data', '-criado_em')
amamentacao_json = [
    {
        "id": o.id,
        "aluno_id": o.aluno_id,
        "aluno": o.aluno.nome if o.aluno else "",
        "turma_id": o.turma_id,
        "turma": o.turma.nome if o.turma else "",
        "data": o.data.strftime("%d/%m/%Y"),
        "horario": str(o.horario) if o.horario else "",
        "quantidade": o.quantidade,
        "motivo": o.motivo or "Mamadeira / Leite Materno",
        "observacao": o.observacao,
        "registrado_por": o.registrado_por.get_full_name() or o.registrado_por.username if o.registrado_por else "",
    }
    for o in amamentacao
]
with open('export_data/5_amamentacao_seami.json', 'w', encoding='utf-8') as f:
    json.dump(amamentacao_json, f, indent=2, ensure_ascii=False)

with open('export_data/5_amamentacao_seami.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(["ID", "Data", "Aluno ID", "Nome da Criança", "Turma ID", "Turma", "Horário", "Qtd Mamadeiras", "Motivo", "Observação", "Registrado por"])
    for o in amamentacao:
        w.writerow([
            o.id, o.data.strftime("%d/%m/%Y"), o.aluno_id or "", o.aluno.nome if o.aluno else "",
            o.turma_id or "", o.turma.nome if o.turma else "", str(o.horario) if o.horario else "",
            o.quantidade, o.motivo or "Mamadeira / Leite Materno", o.observacao,
            o.registrado_por.get_full_name() or o.registrado_por.username if o.registrado_por else "",
        ])

print("Exportando Enfermaria...")
enfermaria = AtendimentoEnfermaria.objects.ativos().select_related('aluno', 'aluno__turma', 'registrado_por').order_by('-data_atendimento', '-horario')
enfermaria_json = [
    {
        "id": at.id,
        "aluno_id": at.aluno_id,
        "aluno_nome": at.aluno.nome,
        "turma_id": at.aluno.turma_id,
        "turma_nome": at.aluno.turma.nome if at.aluno.turma else "",
        "data_atendimento": at.data_atendimento.strftime("%d/%m/%Y"),
        "horario": at.horario.strftime("%H:%M") if at.horario else "",
        "motivo": at.motivo,
        "motivo_detalhado": at.motivo_detalhado or "",
        "cid": at.cid or "",
        "saida_imediata": at.saida_imediata,
        "retornara_dia_seguinte": at.retornara_dia_seguinte,
        "data_retorno_prevista": at.data_retorno_prevista.strftime("%d/%m/%Y") if at.data_retorno_prevista else "",
        "observacoes_medicas": at.observacoes_medicas or "",
        "registrado_por": at.registrado_por.get_full_name() or at.registrado_por.username if at.registrado_por else "",
        "criado_em": timezone.localtime(at.criado_em).strftime("%d/%m/%Y %H:%M:%S") if at.criado_em else "",
    }
    for at in enfermaria
]
with open('export_data/6_enfermaria_seami.json', 'w', encoding='utf-8') as f:
    json.dump(enfermaria_json, f, indent=2, ensure_ascii=False)

with open('export_data/6_enfermaria_seami.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow([
        "ID", "Data", "Horário", "Aluno ID", "Nome da Criança", "Turma ID", "Turma",
        "Motivo Principal", "Motivo Detalhado", "CID", "Saída Imediata", "Retorna no Dia Seguinte",
        "Data Prevista Retorno", "Observações Médicas / Conduta", "Registrado por", "Criado em"
    ])
    for at in enfermaria:
        w.writerow([
            at.id, at.data_atendimento.strftime("%d/%m/%Y"), at.horario.strftime("%H:%M") if at.horario else "",
            at.aluno_id, at.aluno.nome, at.aluno.turma_id or "", at.aluno.turma.nome if at.aluno.turma else "",
            at.motivo, at.motivo_detalhado or "", at.cid or "", "Sim" if at.saida_imediata else "Não",
            "Sim" if at.retornara_dia_seguinte else "Não",
            at.data_retorno_prevista.strftime("%d/%m/%Y") if at.data_retorno_prevista else "",
            at.observacoes_medicas or "",
            at.registrado_por.get_full_name() or at.registrado_por.username if at.registrado_por else "",
            timezone.localtime(at.criado_em).strftime("%d/%m/%Y %H:%M:%S") if at.criado_em else "",
        ])

print("Todos os dados foram exportados com sucesso para export_data/!")
