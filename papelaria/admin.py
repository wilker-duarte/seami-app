from django.contrib import admin
from .models import ItemPapelaria, MovimentacaoEstoque


@admin.register(ItemPapelaria)
class ItemPapelariaAdmin(admin.ModelAdmin):
    list_display = (
        'nome', 'categoria', 'unidade_medida', 'quantidade_estoque', 
        'estoque_minimo', 'solicitar_pais', 'ativo', 'atualizado_em'
    )
    list_filter = ('categoria', 'unidade_medida', 'ativo', 'solicitar_pais')
    search_fields = ('nome', 'especificacao')
    ordering = ('nome',)


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'item', 'tipo', 'quantidade', 'saldo_anterior', 
        'saldo_posterior', 'turma', 'responsavel', 'data', 'criado_em'
    )
    list_filter = ('tipo', 'data', 'turma')
    search_fields = ('item__nome', 'motivo', 'responsavel__username')
    ordering = ('-data', '-criado_em')
