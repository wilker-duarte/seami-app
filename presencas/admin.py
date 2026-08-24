from django.contrib import admin
from core.admin_export import ExportActionMixin
from .models import (
    Turma, Aluno, DiarioDeClasse, RegistroPresenca,
    OcorrenciaCaderno, RegistroAmamentacao, HistoricoFrequenciaMensal,
    AtendimentoEnfermaria
)


class RegistroPresencaInline(admin.TabularInline):
    model = RegistroPresenca
    extra = 0
    fields = ('aluno', 'status', 'observacao')
    readonly_fields = ('aluno',)
    can_delete = False


@admin.register(Turma)
class TurmaAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('nome', 'faixa_etaria', 'get_total_alunos', 'ativo', 'criado_em')
    list_filter = ('ativo',)
    search_fields = ('nome', 'faixa_etaria')
    filter_horizontal = ('professores',)

    def get_total_alunos(self, obj):
        return obj.alunos.count()
    get_total_alunos.short_description = 'Total de Alunos'


@admin.register(Aluno)
class AlunoAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('nome', 'turma', 'turno', 'data_entrada', 'data_desligamento', 'has_acompanhamento', 'ativo')
    list_filter = ('turma', 'turno', 'has_acompanhamento', 'ativo')
    search_fields = ('nome', 'nome_responsavel', 'telefone_responsavel', 'acompanhamento_obs')
    list_editable = ('ativo',)


@admin.register(DiarioDeClasse)
class DiarioDeClasseAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('turma', 'data', 'turno', 'total_presentes', 'total_faltas', 'registrado_por', 'criado_em')
    list_filter = ('turma', 'turno', 'data')
    search_fields = ('turma__nome', 'observacao')
    date_hierarchy = 'data'
    inlines = [RegistroPresencaInline]


@admin.register(RegistroPresenca)
class RegistroPresencaAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('aluno', 'turma', 'data', 'status', 'registrado_por', 'criado_em')
    list_filter = ('status', 'data', 'turma')
    search_fields = ('aluno__nome', 'turma__nome', 'observacao')
    date_hierarchy = 'data'
    list_per_page = 50


from django.utils.html import format_html


@admin.register(OcorrenciaCaderno)
class OcorrenciaCadernoAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('tipo', 'aluno', 'turma', 'data', 'justificado', 'ver_documento', 'registrado_por', 'criado_em')
    list_filter = ('tipo', 'turma', 'justificado', 'data')
    search_fields = ('aluno__nome', 'turma__nome', 'motivo', 'cid', 'observacao', 'attachment_name')
    date_hierarchy = 'data'
    readonly_fields = ('preview_documento',)

    def ver_documento(self, obj):
        if obj.documento:
            return format_html('<a href="{}" target="_blank" style="font-weight: 700; color: #0284c7; text-decoration: underline;">📄 Ver Anexo</a>', obj.documento.url)
        return "-"
    ver_documento.short_description = 'Anexo'

    def preview_documento(self, obj):
        if obj.documento:
            return format_html('<a href="{}" target="_blank" class="button" style="padding: 6px 12px; background: #0284c7; color: white; border-radius: 4px; text-decoration: none; font-weight: bold;">Abrir Documento em Nova Aba</a>', obj.documento.url)
        return "Nenhum arquivo anexado."
    preview_documento.short_description = 'Visualização do Documento'


@admin.register(RegistroAmamentacao)
class RegistroAmamentacaoAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('data', 'quantidade', 'ano', 'mes', 'ver_anexo', 'registrado_por', 'criado_em')
    list_filter = ('ano', 'mes', 'data')
    search_fields = ('observacao', 'attachment_name')
    date_hierarchy = 'data'

    def ver_anexo(self, obj):
        if obj.anexo:
            return format_html('<a href="{}" target="_blank" style="font-weight: 700; color: #db2777; text-decoration: underline;">📄 Ver Anexo</a>', obj.anexo.url)
        return "-"
    ver_anexo.short_description = 'Anexo'


@admin.register(HistoricoFrequenciaMensal)
class HistoricoFrequenciaMensalAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('mes_ano', 'ano', 'mes', 'matriculados', 'presentes_media', 'ausentes_media', 'taxa_frequencia')
    list_filter = ('ano', 'mes')
    search_fields = ('mes_ano', 'observacao')
    ordering = ('-ano', '-mes')


@admin.register(AtendimentoEnfermaria)
class AtendimentoEnfermariaAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('aluno', 'data_atendimento', 'horario', 'motivo', 'saida_imediata', 'retornara_dia_seguinte', 'data_retorno_prevista', 'cid', 'ativo', 'registrado_por')
    list_filter = ('saida_imediata', 'retornara_dia_seguinte', 'ativo', 'data_atendimento', 'motivo')
    search_fields = ('aluno__nome', 'motivo', 'motivo_detalhado', 'cid', 'observacoes_medicas')
    date_hierarchy = 'data_atendimento'


