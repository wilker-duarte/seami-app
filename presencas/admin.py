from django.contrib import admin
from core.admin_export import ExportActionMixin
from .models import Turma, Aluno, DiarioDeClasse, RegistroPresenca, OcorrenciaCaderno


class RegistroPresencaInline(admin.TabularInline):
    model = RegistroPresenca
    extra = 0
    fields = ('aluno', 'status', 'observacao')
    readonly_fields = ('aluno',)
    can_delete = False


@admin.register(Turma)
class TurmaAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('nome', 'faixa_etaria', 'ano_letivo', 'get_total_alunos', 'ativo', 'criado_em')
    list_filter = ('ano_letivo', 'ativo')
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


@admin.register(OcorrenciaCaderno)
class OcorrenciaCadernoAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('tipo', 'aluno', 'turma', 'data', 'justificado', 'registrado_por', 'criado_em')
    list_filter = ('tipo', 'turma', 'justificado', 'data')
    search_fields = ('aluno__nome', 'turma__nome', 'motivo', 'cid', 'observacao')
    date_hierarchy = 'data'

