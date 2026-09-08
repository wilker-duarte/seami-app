from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class UnidadeMedida(models.TextChoices):
    UNIDADE = 'unidade', 'Unidade(s)'
    RESMA = 'resma', 'Resma(s)'
    CARTELA = 'cartela', 'Cartela(s)'
    LITRO = 'litro', 'Litro(s) / Frasco(s)'
    CAIXA = 'caixa', 'Caixa(s)'
    PACOTE = 'pacote', 'Pacote(s)'
    BLOCO = 'bloco', 'Bloco(s)'
    ROLO = 'rolo', 'Rolo(s)'
    METRO = 'metro', 'Metro(s)'
    KIT = 'kit', 'Kit / Conjunto'


class CategoriaItem(models.TextChoices):
    PAPEIS = 'papeis', 'Papéis e Cartolinas'
    COLAS = 'colas', 'Colas e Adesivos'
    PINTURA = 'pintura', 'Pintura e Desenho'
    ESCRITORIO = 'escritorio', 'Material de Escritório'
    HIGIENE = 'higiene', 'Higiene e Cuidados'
    DECORACAO = 'decoracao', 'Decoração e Eventos'
    DIVERSOS = 'diversos', 'Diversos'


class ObservacaoPaisTipo(models.TextChoices):
    NENHUMA = '', 'Sem nota de rodapé'
    SUGESTAO_MARCA = 'sugestao_marca', '(*) Sugestão de marca'
    HIGIENE_ENFERMAGEM = 'higiene_enfermagem', '(**) Higienização / Enfermagem / Berçário'


class TipoMovimentacao(models.TextChoices):
    ENTRADA = 'ENTRADA', 'Entrada (Compra / Doação)'
    SAIDA = 'SAIDA', 'Saída (Consumo Pedagógico / Sala)'
    AJUSTE = 'AJUSTE', 'Ajuste de Inventário'


class ItemPapelaria(models.Model):
    nome = models.CharField(max_length=150, verbose_name='Nome do Item')
    especificacao = models.TextField(blank=True, verbose_name='Especificação / Detalhes / Marca')
    categoria = models.CharField(
        max_length=30,
        choices=CategoriaItem.choices,
        default=CategoriaItem.DIVERSOS,
        verbose_name='Categoria'
    )
    unidade_medida = models.CharField(
        max_length=30,
        choices=UnidadeMedida.choices,
        default=UnidadeMedida.UNIDADE,
        verbose_name='Unidade de Medida'
    )
    quantidade_estoque = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Saldo Atual em Estoque'
    )
    estoque_minimo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name='Estoque Mínimo'
    )
    solicitar_pais = models.BooleanField(
        default=True,
        verbose_name='Incluir na Lista dos Pais',
        help_text='Indica se este item aparecerá no relatório oficial enviado aos pais.'
    )
    quantidade_sugerida_pais = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Quantidade Sugerida aos Pais',
        help_text='Exemplo: 01 unidade, 02 caixas, 04 de cada cor, 20 cartelas'
    )
    observacao_pais_tipo = models.CharField(
        max_length=30,
        choices=ObservacaoPaisTipo.choices,
        default=ObservacaoPaisTipo.NENHUMA,
        blank=True,
        verbose_name='Nota de Rodapé para Pais'
    )
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens_papelaria_cadastrados',
        verbose_name='Cadastrado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        verbose_name = 'Item de Papelaria'
        verbose_name_plural = 'Itens de Papelaria'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['nome']),
            models.Index(fields=['categoria']),
            models.Index(fields=['ativo']),
            models.Index(fields=['solicitar_pais']),
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_unidade_medida_display()})"

    @property
    def is_estoque_zerado(self):
        return self.quantidade_estoque <= Decimal('0.00')

    @property
    def is_estoque_baixo(self):
        return Decimal('0.00') < self.quantidade_estoque <= self.estoque_minimo

    @property
    def status_estoque_badge(self):
        if self.is_estoque_zerado:
            return {
                'label': 'Zerado',
                'bg': '#fee2e2',
                'color': '#dc2626',
                'border': '#fca5a5',
                'icon': 'alert-circle'
            }
        elif self.is_estoque_baixo:
            return {
                'label': 'Estoque Baixo',
                'bg': '#fef3c7',
                'color': '#d97706',
                'border': '#fcd34d',
                'icon': 'alert-triangle'
            }
        else:
            return {
                'label': 'Normal',
                'bg': '#dcfce7',
                'color': '#16a34a',
                'border': '#86efac',
                'icon': 'check-circle-2'
            }


class MovimentacaoEstoque(models.Model):
    item = models.ForeignKey(
        ItemPapelaria,
        on_delete=models.CASCADE,
        related_name='movimentacoes',
        verbose_name='Item'
    )
    tipo = models.CharField(
        max_length=20,
        choices=TipoMovimentacao.choices,
        verbose_name='Tipo de Movimentação'
    )
    quantidade = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Quantidade'
    )
    saldo_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Saldo Anterior'
    )
    saldo_posterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Saldo Posterior'
    )
    turma = models.ForeignKey(
        'presencas.Turma',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consumos_papelaria',
        verbose_name='Turma / Sala Destino (para Saídas)'
    )
    aluno = models.ForeignKey(
        'presencas.Aluno',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='doacoes_papelaria',
        verbose_name='Aluno Doador (para Entradas)'
    )
    motivo = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Motivo / Observação'
    )
    data = models.DateField(default=timezone.now, verbose_name='Data')
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimentacoes_estoque',
        verbose_name='Responsável pelo Registro'
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Registrado em')

    class Meta:
        verbose_name = 'Movimentação de Estoque'
        verbose_name_plural = 'Movimentações de Estoque'
        ordering = ['-data', '-criado_em']
        indexes = [
            models.Index(fields=['item', 'data']),
            models.Index(fields=['tipo', 'data']),
        ]

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.quantidade} {self.item.get_unidade_medida_display()} de {self.item.nome} em {self.data.strftime('%d/%m/%Y')}"
