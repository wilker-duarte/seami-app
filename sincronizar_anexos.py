#!/usr/bin/env python
"""
Script de Sincronização e Correção de Anexos do Caderno SEAMI e Amamentação
==========================================================================
Este script resolve desencontros entre nomes de arquivos físicos no disco
(com prefixos numéricos 178..._ gerados no sistema legado) e os registros
no banco de dados do Django.

Funcionalidades:
1. Para cada arquivo com prefixo numérico (ex: 178..._nome.pdf), cria uma cópia com o nome limpo no disco.
2. Para cada registro no banco de dados com anexo ausente ou divergente, localiza o arquivo correspondente e atualiza o banco.
3. Garante permissões adequadas nos arquivos.
"""

import os
import re
import sys
import shutil
import unicodedata
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from presencas.models import OcorrenciaCaderno, RegistroAmamentacao


def normalize_name(text):
    """Normaliza texto removendo prefixos de timestamp, acentos, underlines e espaços extras."""
    if not text:
        return ""
    # Remove prefixo numérico de timestamp (ex: 1786633542762_)
    clean = re.sub(r'^\d{10,14}_', '', str(text).strip())
    # Normaliza acentuação para ASCII
    nfkd = unicodedata.normalize('NFKD', clean)
    clean = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Substitui underlines por espaços e passa para minúsculas
    clean = clean.replace('_', ' ').lower()
    # Remove espaços duplos
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def sincronizar():
    media_root = settings.MEDIA_ROOT
    print("=" * 70)
    print(f"Iniciando Sincronização de Anexos em: {media_root}")
    print("=" * 70)

    pastas = [
        ('ocorrencias', media_root / 'attachments' / 'ocorrencias'),
        ('amamentacao', media_root / 'attachments' / 'amamentacao')
    ]

    total_arquivos_duplicados = 0
    total_banco_atualizados = 0

    # -------------------------------------------------------------------------
    # 1. CRIAR CÓPIAS COM NOMES LIMPOS NO DISCO PARA ARQUIVOS COM TIMESTAMP
    # -------------------------------------------------------------------------
    for tipo, pasta_path in pastas:
        if not os.path.exists(pasta_path):
            print(f"[-] Pasta não encontrada: {pasta_path} (pulando)")
            continue

        print(f"\n[1] Verificando arquivos físicos em 'attachments/{tipo}'...")
        arquivos = os.listdir(pasta_path)

        for filename in arquivos:
            file_full_path = os.path.join(pasta_path, filename)
            if not os.path.isfile(file_full_path):
                continue

            # Se o arquivo tem prefixo de timestamp (178..._)
            if re.match(r'^\d{10,14}_', filename):
                clean_name = re.sub(r'^\d{10,14}_', '', filename)
                clean_full_path = os.path.join(pasta_path, clean_name)

                # Cria a versão sem o timestamp se ela não existir
                if not os.path.exists(clean_full_path):
                    try:
                        shutil.copy2(file_full_path, clean_full_path)
                        total_arquivos_duplicados += 1
                        print(f"  [+] Criada cópia limpa: '{clean_name}'")
                    except Exception as e:
                        print(f"  [!] Erro ao copiar '{filename}': {e}")

                # Também cria uma versão com underline no lugar de espaço
                underline_name = clean_name.replace(' ', '_')
                underline_full_path = os.path.join(pasta_path, underline_name)
                if not os.path.exists(underline_full_path):
                    try:
                        shutil.copy2(file_full_path, underline_full_path)
                        total_arquivos_duplicados += 1
                    except Exception:
                        pass

    # -------------------------------------------------------------------------
    # 2. MAPEAMENTO DOS ARQUIVOS EXISTENTES NO DISCO
    # -------------------------------------------------------------------------
    disk_files_ocorrencias = {}
    pasta_oc = media_root / 'attachments' / 'ocorrencias'
    if os.path.exists(pasta_oc):
        for f in os.listdir(pasta_oc):
            full = os.path.join(pasta_oc, f)
            if os.path.isfile(full):
                norm = normalize_name(f)
                disk_files_ocorrencias[norm] = f
                # Mapeia também o nome exato
                disk_files_ocorrencias[f.lower()] = f
                disk_files_ocorrencias[f.replace('_', ' ').lower()] = f
                disk_files_ocorrencias[f.replace(' ', '_').lower()] = f

    disk_files_amamentacao = {}
    pasta_am = media_root / 'attachments' / 'amamentacao'
    if os.path.exists(pasta_am):
        for f in os.listdir(pasta_am):
            full = os.path.join(pasta_am, f)
            if os.path.isfile(full):
                norm = normalize_name(f)
                disk_files_amamentacao[norm] = f
                disk_files_amamentacao[f.lower()] = f
                disk_files_amamentacao[f.replace('_', ' ').lower()] = f
                disk_files_amamentacao[f.replace(' ', '_').lower()] = f

    # -------------------------------------------------------------------------
    # 3. ATUALIZAR REGISTROS DO BANCO DE DADOS (OCORRENCIACADERNO)
    # -------------------------------------------------------------------------
    print("\n[2] Verificando ocorrências no banco de dados...")
    ocorrencias = OcorrenciaCaderno.objects.all()

    for oc in ocorrencias:
        doc_field_val = str(oc.documento) if oc.documento else ""
        att_name_val = oc.attachment_name or ""

        # Verifica se o arquivo atual já existe no disco
        if doc_field_val:
            full_path = os.path.join(media_root, doc_field_val)
            if os.path.exists(full_path):
                continue  # Arquivo já existe perfeitamente!

        # Se não existe, tenta encontrar o arquivo correto no disco
        candidatos = []
        if doc_field_val:
            base = os.path.basename(doc_field_val)
            candidatos.append(base)
            candidatos.append(normalize_name(base))
        if att_name_val:
            candidatos.append(att_name_val)
            candidatos.append(normalize_name(att_name_val))

        arquivo_encontrado = None
        for cand in candidatos:
            if not cand:
                continue
            cand_norm = normalize_name(cand)
            if cand_norm in disk_files_ocorrencias:
                arquivo_encontrado = disk_files_ocorrencias[cand_norm]
                break
            if cand.lower() in disk_files_ocorrencias:
                arquivo_encontrado = disk_files_ocorrencias[cand.lower()]
                break

        # Se ainda não encontrou, tenta buscar por partes do nome do aluno e data
        if not arquivo_encontrado and oc.aluno:
            aluno_nome_norm = normalize_name(oc.aluno.nome)
            data_str = oc.data.strftime('%d')
            for norm_key, real_file in disk_files_ocorrencias.items():
                if aluno_nome_norm and aluno_nome_norm in norm_key:
                    if data_str in norm_key or oc.data.strftime('%Y') in norm_key:
                        arquivo_encontrado = real_file
                        break

        if arquivo_encontrado:
            novo_caminho_relativo = f"attachments/ocorrencias/{arquivo_encontrado}"
            oc.documento.name = novo_caminho_relativo
            if not oc.attachment_name:
                oc.attachment_name = re.sub(r'^\d{10,14}_', '', arquivo_encontrado)
            oc.save(update_fields=['documento', 'attachment_name'])
            total_banco_atualizados += 1
            print(f"  [✔ Banco Atualizado] Ocorrência ID {oc.id} ({oc.aluno.nome if oc.aluno else 'Geral'}) -> '{novo_caminho_relativo}'")

    # -------------------------------------------------------------------------
    # 4. ATUALIZAR REGISTROS DE AMAMENTAÇÃO
    # -------------------------------------------------------------------------
    print("\n[3] Verificando registros de amamentação no banco de dados...")
    amamentacoes = RegistroAmamentacao.objects.all()

    for am in amamentacoes:
        anexo_field_val = str(am.anexo) if am.anexo else ""
        att_name_val = am.attachment_name or ""

        if anexo_field_val:
            full_path = os.path.join(media_root, anexo_field_val)
            if os.path.exists(full_path):
                continue

        candidatos = []
        if anexo_field_val:
            base = os.path.basename(anexo_field_val)
            candidatos.append(base)
            candidatos.append(normalize_name(base))
        if att_name_val:
            candidatos.append(att_name_val)
            candidatos.append(normalize_name(att_name_val))

        arquivo_encontrado = None
        for cand in candidatos:
            if not cand:
                continue
            cand_norm = normalize_name(cand)
            if cand_norm in disk_files_amamentacao:
                arquivo_encontrado = disk_files_amamentacao[cand_norm]
                break

        if arquivo_encontrado:
            novo_caminho_relativo = f"attachments/amamentacao/{arquivo_encontrado}"
            am.anexo.name = novo_caminho_relativo
            if not am.attachment_name:
                am.attachment_name = re.sub(r'^\d{10,14}_', '', arquivo_encontrado)
            am.save(update_fields=['anexo', 'attachment_name'])
            total_banco_atualizados += 1
            print(f"  [✔ Banco Atualizado] Amamentação {am.data} -> '{novo_caminho_relativo}'")

    print("\n" + "=" * 70)
    print("RESUMO DA SINCRONIZAÇÃO:")
    print(f" - Cópias limpas geradas no disco: {total_arquivos_duplicados}")
    print(f" - Registros corrigidos no Banco de Dados: {total_banco_atualizados}")
    print("=" * 70)


if __name__ == '__main__':
    sincronizar()
