from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, Count
from django.utils import timezone
from decimal import Decimal
import json

from .models import (
    ItemPapelaria, MovimentacaoEstoque, UnidadeMedida, 
    CategoriaItem, ObservacaoPaisTipo, TipoMovimentacao
)
from presencas.models import Turma, Aluno


def is_master_user(user):
    return user.is_authenticated and (getattr(user, 'is_master_admin', False) or user.is_superuser)


@login_required
def estoque_papelaria_view(request):
    """
    Painel Principal de Gestão do Estoque de Papelaria e Lista de Itens.
    Permite listagem, filtros, inclusão/edição de itens e registro de movimentações.
    """
    can_manage = is_master_user(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        # -------------------------------------------------------------
        # AÇÕES DE CADASTRO / EDIÇÃO DE ITENS (Exclusivo Master Admin)
        # -------------------------------------------------------------
        if action in ['create_item', 'update_item']:
            if not can_manage:
                messages.error(request, "Apenas o Administrador Master tem permissão para cadastrar ou editar itens da papelaria.")
                return redirect('papelaria:estoque')

            nome = request.POST.get('nome', '').strip()
            especificacao = request.POST.get('especificacao', '').strip()
            categoria = request.POST.get('categoria', CategoriaItem.DIVERSOS)
            unidade_medida = request.POST.get('unidade_medida', UnidadeMedida.UNIDADE)
            solicitar_pais = request.POST.get('solicitar_pais') == 'on'
            quantidade_sugerida_pais = request.POST.get('quantidade_sugerida_pais', '').strip()
            observacao_pais_tipo = request.POST.get('observacao_pais_tipo', '')

            try:
                estoque_minimo = Decimal(request.POST.get('estoque_minimo', '5').replace(',', '.'))
            except Exception:
                estoque_minimo = Decimal('5.00')

            if not nome:
                messages.error(request, "O nome do item é obrigatório.")
                return redirect('papelaria:estoque')

            if action == 'create_item':
                try:
                    saldo_inicial = Decimal(request.POST.get('quantidade_estoque', '0').replace(',', '.'))
                except Exception:
                    saldo_inicial = Decimal('0.00')

                item = ItemPapelaria.objects.create(
                    nome=nome,
                    especificacao=especificacao,
                    categoria=categoria,
                    unidade_medida=unidade_medida,
                    quantidade_estoque=saldo_inicial,
                    estoque_minimo=estoque_minimo,
                    solicitar_pais=solicitar_pais,
                    quantidade_sugerida_pais=quantidade_sugerida_pais,
                    observacao_pais_tipo=observacao_pais_tipo,
                    cadastrado_por=request.user
                )

                # Se houver saldo inicial > 0, gera movimentação de entrada inicial
                if saldo_inicial > 0:
                    MovimentacaoEstoque.objects.create(
                        item=item,
                        tipo=TipoMovimentacao.ENTRADA,
                        quantidade=saldo_inicial,
                        saldo_anterior=Decimal('0.00'),
                        saldo_posterior=saldo_inicial,
                        motivo="Saldo inicial de implantação de estoque",
                        responsavel=request.user
                    )

                messages.success(request, f"Item '{item.nome}' cadastrado com sucesso!")

            elif action == 'update_item':
                item_id = request.POST.get('item_id')
                item = get_object_or_404(ItemPapelaria, id=item_id)
                item.nome = nome
                item.especificacao = especificacao
                item.categoria = categoria
                item.unidade_medida = unidade_medida
                item.estoque_minimo = estoque_minimo
                item.solicitar_pais = solicitar_pais
                item.quantidade_sugerida_pais = quantidade_sugerida_pais
                item.observacao_pais_tipo = observacao_pais_tipo
                item.save()

                messages.success(request, f"Item '{item.nome}' atualizado com sucesso!")

            return redirect('papelaria:estoque')

        # -------------------------------------------------------------
        # AÇÃO DE MOVIMENTAÇÃO DE ESTOQUE (Entrada, Saída ou Ajuste)
        # -------------------------------------------------------------
        elif action == 'movimentar_estoque':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(ItemPapelaria, id=item_id)
            tipo_mov = request.POST.get('tipo_movimentacao')

            try:
                qtd_mov = Decimal(request.POST.get('quantidade', '0').replace(',', '.'))
            except Exception:
                qtd_mov = Decimal('0.00')

            if qtd_mov <= 0:
                messages.error(request, "A quantidade para movimentação deve ser maior que zero.")
                return redirect('papelaria:estoque')

            turma_id = request.POST.get('turma_id')
            aluno_id = request.POST.get('aluno_id')
            motivo = request.POST.get('motivo', '').strip()
            data_mov = request.POST.get('data_movimentacao') or timezone.now().date()

            turma = Turma.objects.filter(id=turma_id).first() if turma_id else None
            aluno = Aluno.objects.filter(id=aluno_id).first() if aluno_id else None

            saldo_anterior = item.quantidade_estoque

            if tipo_mov == TipoMovimentacao.ENTRADA:
                saldo_posterior = saldo_anterior + qtd_mov
                item.quantidade_estoque = saldo_posterior
                item.save()

            elif tipo_mov == TipoMovimentacao.SAIDA:
                if qtd_mov > saldo_anterior:
                    messages.error(
                        request, 
                        f"Saldo insuficiente em estoque! Saldo disponível: {saldo_anterior} {item.get_unidade_medida_display()}. Quantidade solicitada: {qtd_mov}."
                    )
                    return redirect('papelaria:estoque')

                saldo_posterior = saldo_anterior - qtd_mov
                item.quantidade_estoque = saldo_posterior
                item.save()

            elif tipo_mov == TipoMovimentacao.AJUSTE:
                # Ajuste direto para a nova quantidade inventariada
                saldo_posterior = qtd_mov
                item.quantidade_estoque = saldo_posterior
                item.save()
            else:
                messages.error(request, "Tipo de movimentação inválido.")
                return redirect('papelaria:estoque')

            MovimentacaoEstoque.objects.create(
                item=item,
                tipo=tipo_mov,
                quantidade=qtd_mov,
                saldo_anterior=saldo_anterior,
                saldo_posterior=saldo_posterior,
                turma=turma,
                aluno=aluno,
                motivo=motivo,
                data=data_mov,
                responsavel=request.user
            )

            tipo_nome = "Entrada" if tipo_mov == TipoMovimentacao.ENTRADA else ("Saída" if tipo_mov == TipoMovimentacao.SAIDA else "Ajuste")
            messages.success(request, f"{tipo_nome} de {qtd_mov} {item.get_unidade_medida_display()} de '{item.nome}' registrada com sucesso!")
            return redirect('papelaria:estoque')

        # -------------------------------------------------------------
        # AÇÃO: ATIVAR / DESATIVAR ITEM (Master Admin)
        # -------------------------------------------------------------
        elif action == 'toggle_ativo':
            if not can_manage:
                messages.error(request, "Permissão negada.")
                return redirect('papelaria:estoque')

            item_id = request.POST.get('item_id')
            item = get_object_or_404(ItemPapelaria, id=item_id)
            item.ativo = not item.ativo
            item.save()
            status_str = "ativado" if item.ativo else "desativado"
            messages.success(request, f"Item '{item.nome}' foi {status_str} com sucesso.")
            return redirect('papelaria:estoque')

        # -------------------------------------------------------------
        # AÇÃO: EXCLUIR ITEM (Master Admin)
        # -------------------------------------------------------------
        elif action == 'delete_item':
            if not can_manage:
                messages.error(request, "Permissão negada.")
                return redirect('papelaria:estoque')

            item_id = request.POST.get('item_id')
            item = get_object_or_404(ItemPapelaria, id=item_id)
            nome_removido = item.nome
            item.delete()
            messages.success(request, f"Item '{nome_removido}' excluído com sucesso do estoque.")
            return redirect('papelaria:estoque')

    # -----------------------------------------------------------------
    # CONSULTA E FILTROS (GET)
    # -----------------------------------------------------------------
    search = request.GET.get('search', '').strip()
    categoria_filter = request.GET.get('categoria', '')
    status_filter = request.GET.get('status', '')
    lista_pais_filter = request.GET.get('lista_pais', '')

    itens_qs = ItemPapelaria.objects.all().select_related('cadastrado_por')

    if search:
        itens_qs = itens_qs.filter(
            Q(nome__icontains=search) |
            Q(especificacao__icontains=search) |
            Q(quantidade_sugerida_pais__icontains=search)
        )

    if categoria_filter:
        itens_qs = itens_qs.filter(categoria=categoria_filter)

    if lista_pais_filter == 'sim':
        itens_qs = itens_qs.filter(solicitar_pais=True)
    elif lista_pais_filter == 'nao':
        itens_qs = itens_qs.filter(solicitar_pais=False)

    # Coleta de totais para métricas gerais
    all_itens = list(ItemPapelaria.objects.filter(ativo=True))
    total_itens = len(all_itens)
    total_zerados = sum(1 for i in all_itens if i.is_estoque_zerado)
    total_baixos = sum(1 for i in all_itens if i.is_estoque_baixo)
    total_lista_pais = sum(1 for i in all_itens if i.solicitar_pais)

    # Filtragem em memória por status do estoque se especificado
    itens_list = []
    for item in itens_qs.order_by('nome'):
        if status_filter == 'zerado' and not item.is_estoque_zerado:
            continue
        elif status_filter == 'baixo' and not item.is_estoque_baixo:
            continue
        elif status_filter == 'normal' and (item.is_estoque_baixo or item.is_estoque_zerado):
            continue
        itens_list.append(item)

    # Movimentações recentes para o log do dashboard
    recent_movimentacoes = (
        MovimentacaoEstoque.objects.all()
        .select_related('item', 'turma', 'aluno', 'responsavel')
        .order_by('-data', '-criado_em')[:15]
    )

    turmas = Turma.objects.filter(ativo=True).order_by('nome')
    alunos = Aluno.objects.filter(ativo=True).select_related('turma').order_by('nome')

    context = {
        'itens': itens_list,
        'total_itens': total_itens,
        'total_zerados': total_zerados,
        'total_baixos': total_baixos,
        'total_lista_pais': total_lista_pais,
        'recent_movimentacoes': recent_movimentacoes,
        'categorias': CategoriaItem.choices,
        'unidades_medida': UnidadeMedida.choices,
        'observacoes_pais_tipos': ObservacaoPaisTipo.choices,
        'turmas': turmas,
        'alunos': alunos,
        'can_manage': can_manage,
        'search': search,
        'selected_categoria': categoria_filter,
        'selected_status': status_filter,
        'selected_lista_pais': lista_pais_filter,
        'today': timezone.now().date().isoformat(),
        'active_tab': 'papelaria',
        'active_module': 'estoque',
    }

    return render(request, 'papelaria/estoque.html', context)


@login_required
def relatorio_pais_view(request):
    """
    Relatório Oficial da Lista de Material Escolar para envio aos Pais/Responsáveis.
    Contém a estrutura, cabeçalho e notas de rodapé institucionais do SEAMI (lista_de_material.md)
    e preenchimento dinâmico com os itens cadastrados no módulo de papelaria marcados para a lista.
    """
    itens_pais = ItemPapelaria.objects.filter(
        ativo=True,
        solicitar_pais=True
    ).order_by('categoria', 'nome')

    # Agrupamento opcional por categoria
    itens_por_categoria = {}
    for item in itens_pais:
        cat_nome = item.get_categoria_display()
        if cat_nome not in itens_por_categoria:
            itens_por_categoria[cat_nome] = []
        itens_por_categoria[cat_nome].append(item)

    context = {
        'itens_pais': itens_pais,
        'itens_por_categoria': itens_por_categoria,
        'total_itens': itens_pais.count(),
        'today': timezone.now().date(),
        'ano_atual': timezone.now().year,
        'active_tab': 'papelaria',
        'active_module': 'relatorio_pais',
    }

    return render(request, 'papelaria/relatorio_pais.html', context)


@login_required
def historico_item_json(request, item_id):
    """
    Retorna o histórico de movimentações de um item específico em JSON
    para ser exibido na modal interativa da tabela.
    """
    item = get_object_or_404(ItemPapelaria, id=item_id)
    movs = (
        MovimentacaoEstoque.objects.filter(item=item)
        .select_related('turma', 'aluno', 'responsavel')
        .order_by('-data', '-criado_em')[:50]
    )

    data = {
        'item_nome': item.nome,
        'unidade': item.get_unidade_medida_display(),
        'saldo_atual': str(item.quantidade_estoque),
        'estoque_minimo': str(item.estoque_minimo),
        'movimentacoes': [
            {
                'id': m.id,
                'data': m.data.strftime('%d/%m/%Y'),
                'tipo': m.tipo,
                'tipo_display': m.get_tipo_display(),
                'quantidade': str(m.quantidade),
                'saldo_anterior': str(m.saldo_anterior),
                'saldo_posterior': str(m.saldo_posterior),
                'turma': m.turma.nome if m.turma else None,
                'aluno': m.aluno.nome if m.aluno else None,
                'motivo': m.motivo or '-',
                'responsavel': m.responsavel.get_full_name() or m.responsavel.username if m.responsavel else 'Sistema'
            }
            for m in movs
        ]
    }

    return JsonResponse(data)
