#!/usr/bin/env python
"""
Script para Identificar Ocorrências com Anexos Ausentes (404)
============================================================
Varre todos os registros do Caderno SEAMI e de Amamentação e verifica
se o anexo físico existe no disco (utilizando a mesma lógica de busca
inteligente do sistema).
"""

import os
import re
import unicodedata
from urllib.parse import unquote
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from presencas.models import OcorrenciaCaderno, RegistroAmamentacao


def normalize_media_filename(text):
    if not text:
        return ""
    text = unquote(str(text))
    clean = re.sub(r'^\d{10,14}_', '', text.strip())
    clean = re.sub(r'_[a-zA-Z0-9]{7}(\.[a-zA-Z0-9]+)$', r'\1', clean)
    nfkd = unicodedata.normalize('NFKD', clean)
    clean = ''.join(c for c in nfkd if not unicodedata.combining(c))
    clean = clean.replace('_', ' ').replace('-', ' ').lower()
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def arquivo_existe_ou_encontra(relative_path):
    """Verifica se o arquivo existe ou pode ser resolvido no disco."""
    if not relative_path:
        return False, None

    clean_path = unquote(str(relative_path).strip())
    full_path = os.path.abspath(os.path.join(str(settings.MEDIA_ROOT), clean_path))

    # 1. Caminho Exato
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return True, clean_path

    # 2. Busca Inteligente no Diretório
    dir_name = os.path.dirname(full_path)
    file_name = os.path.basename(clean_path)

    if os.path.exists(dir_name) and os.path.isdir(dir_name):
        norm_target = normalize_media_filename(file_name)
        target_base, target_ext = os.path.splitext(file_name)
        norm_target_base = normalize_media_filename(target_base)

        arquivos_disco = [f for f in os.listdir(dir_name) if os.path.isfile(os.path.join(dir_name, f))]

        for f in arquivos_disco:
            f_clean = re.sub(r'^\d{10,14}_', '', f)
            if f_clean.lower() == file_name.lower() or f_clean.replace(' ', '_').lower() == file_name.lower() or f_clean.replace('_', ' ').lower() == file_name.lower():
                return True, os.path.join(os.path.relpath(dir_name, str(settings.MEDIA_ROOT)), f).replace('\\', '/')

        for f in arquivos_disco:
            if normalize_media_filename(f) == norm_target:
                return True, os.path.join(os.path.relpath(dir_name, str(settings.MEDIA_ROOT)), f).replace('\\', '/')

        for f in arquivos_disco:
            f_base, f_ext = os.path.splitext(f)
            if normalize_media_filename(f_base) == norm_target_base:
                return True, os.path.join(os.path.relpath(dir_name, str(settings.MEDIA_ROOT)), f).replace('\\', '/')

        if norm_target_base and len(norm_target_base) > 4:
            for f in arquivos_disco:
                f_base, f_ext = os.path.splitext(f)
                f_norm_base = normalize_media_filename(f_base)
                if (norm_target_base in f_norm_base or f_norm_base in norm_target_base) and (not target_ext or target_ext.lower() == f_ext.lower()):
                    return True, os.path.join(os.path.relpath(dir_name, str(settings.MEDIA_ROOT)), f).replace('\\', '/')

    return False, None


def verificar():
    print("=" * 95)
    print("VARREDURA DE ANEXOS DO CADERNO SEAMI (IDENTIFICAÇÃO DE 404)")
    print("=" * 95)

    # 1. Ocorrências do Caderno SEAMI
    ocorrencias_com_anexo = OcorrenciaCaderno.objects.exclude(documento='').exclude(documento__isnull=True)
    total_oc = ocorrencias_com_anexo.count()

    faltantes_oc = []
    encontrados_oc = 0

    for oc in ocorrencias_com_anexo:
        existe, path_encontrado = arquivo_existe_ou_encontra(oc.documento.name)
        if existe:
            encontrados_oc += 1
        else:
            faltantes_oc.append({
                'id': oc.id,
                'tipo': oc.get_tipo_display(),
                'aluno': oc.aluno.nome if oc.aluno else "Não especificado",
                'turma': oc.turma.nome if oc.turma else "-",
                'data': oc.data.strftime('%d/%m/%Y'),
                'anexo_banco': oc.documento.name,
                'nome_original': oc.attachment_name or "-"
            })

    # 2. Amamentação
    amamentacao_com_anexo = RegistroAmamentacao.objects.exclude(anexo='').exclude(anexo__isnull=True)
    total_am = amamentacao_com_anexo.count()

    faltantes_am = []
    encontrados_am = 0

    for am in amamentacao_com_anexo:
        existe, path_encontrado = arquivo_existe_ou_encontra(am.anexo.name)
        if existe:
            encontrados_am += 1
        else:
            faltantes_am.append({
                'id': am.id,
                'tipo': 'Amamentação',
                'aluno': 'Sala de Amamentação',
                'turma': '-',
                'data': am.data.strftime('%d/%m/%Y'),
                'anexo_banco': am.anexo.name,
                'nome_original': am.attachment_name or "-"
            })

    # EXIBIÇÃO DOS RESULTADOS
    todos_faltantes = faltantes_oc + faltantes_am

    print(f"\nTotal de registros com anexo analisados: {total_oc + total_am}")
    print(f"  ✔ Anexos encontrados e funcionando: {encontrados_oc + encontrados_am}")
    print(f"  ❌ Anexos que retornam 404 (Não encontrados no disco): {len(todos_faltantes)}\n")

    if not todos_faltantes:
        print("🎉 PARABÉNS! Todos os anexos cadastrados foram encontrados no disco. Nenhum 404 detectado.")
    else:
        print("-" * 95)
        print(f"{'ID':<6} | {'TIPO':<10} | {'DATA':<10} | {'ALUNO':<28} | {'TURMA':<10} | {'ARQUIVO PROCURADO'}")
        print("-" * 95)
        for item in todos_faltantes:
            print(f"{item['id']:<6} | {item['tipo']:<10} | {item['data']:<10} | {item['aluno'][:28]:<28} | {item['turma']:<10} | {os.path.basename(item['anexo_banco'])}")
        print("-" * 95)

    print("=" * 95)


if __name__ == '__main__':
    verificar()
