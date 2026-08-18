from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Count, Q


class StatusPresenca(models.TextChoices):
    PRESENTE = 'PRESENTE', 'Presente (P)'
    AUSENTE = 'AUSENTE', 'Falta (F)'
    JUSTIFICADO = 'JUSTIFICADO', 'Falta Justificada (FJ)'
    RECESSO = 'RECESSO', 'Recesso Escolar (RE)'
    FERIADO = 'FERIADO', 'Feriado (FE)'


class TurnoAluno(models.TextChoices):
    INTEGRAL = 'integral', 'Integral'
    MATUTINO = 'matutino', 'Matutino'
    VESPERTINO = 'vespertino', 'Vespertino'


class TurnoFiltro(models.TextChoices):
    TODOS = 'all', 'Todos os Turnos'
    INTEGRAL = 'integral', 'Integral'
    MATUTINO = 'matutino', 'Matutino'
    VESPERTINO = 'vespertino', 'Vespertino'


class Turma(models.Model):
    nome = models.CharField(max_length=100, unique=True, verbose_name='Nome da Turma / Sala')
    faixa_etaria = models.CharField(max_length=50, blank=True, verbose_name='Faixa Etária')
    ano_letivo = models.IntegerField(default=2026, verbose_name='Ano Letivo')
    professores = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='turmas',
        blank=True,
        verbose_name='Professores Responsáveis'
    )
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Turma'
        verbose_name_plural = 'Turmas'
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.ano_letivo})"


class Aluno(models.Model):
    nome = models.CharField(max_length=150, verbose_name='Nome da Criança')
    data_nascimento = models.DateField(null=True, blank=True, verbose_name='Data de Nascimento')
    turma = models.ForeignKey(
        Turma,
        on_delete=models.PROTECT,
        related_name='alunos',
        verbose_name='Turma / Sala'
    )
    turno = models.CharField(
        max_length=20,
        choices=TurnoAluno.choices,
        default=TurnoAluno.INTEGRAL,
        verbose_name='Turno'
    )
    data_entrada = models.DateField(null=True, blank=True, verbose_name='Data de Entrada')
    data_desligamento = models.DateField(null=True, blank=True, verbose_name='Data de Desligamento')
    motivo_desligamento = models.TextField(blank=True, verbose_name='Motivo do Desligamento')
    has_acompanhamento = models.BooleanField(default=False, verbose_name='Possui Acompanhamento Especial')
    acompanhamento_obs = models.TextField(blank=True, verbose_name='Observações de Acompanhamento')
    acompanhamento_dias = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Dias de Acompanhamento',
        help_text='Dias da semana separados por vírgula. Ex: seg,qua,sex'
    )
    nome_responsavel = models.CharField(max_length=150, blank=True, verbose_name='Nome do Responsável')
    telefone_responsavel = models.CharField(max_length=20, blank=True, verbose_name='Telefone do Responsável')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Aluno'
        verbose_name_plural = 'Alunos'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['turma', 'ativo']),
            models.Index(fields=['data_entrada']),
        ]

    def __str__(self):
        return f"{self.nome} - Sala {self.turma.nome}"

    @property
    def is_ativo_hoje(self):
        today = timezone.localdate()
        if not self.ativo:
            return False
        if self.data_entrada and self.data_entrada > today:
            return False
        if self.data_desligamento and self.data_desligamento < today:
            return False
        return True


class DiarioDeClasse(models.Model):
    """
    Representa a Sessão de Diário de Classe do dia letivo (100% Relacional).
    """
    turma = models.ForeignKey(
        Turma,
        on_delete=models.PROTECT,
        related_name='diarios',
        verbose_name='Turma / Sala'
    )
    data = models.DateField(default=timezone.now, verbose_name='Data da Aula')
    turno = models.CharField(
        max_length=20,
        choices=TurnoFiltro.choices,
        default=TurnoFiltro.TODOS,
        verbose_name='Turno do Lançamento'
    )
    observacao = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observações do Dia',
        help_text='Anotações gerais sobre o dia da turma (ocorrências, avisos, etc.)'
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diarios_registrados',
        verbose_name='Registrado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Diário de Classe'
        verbose_name_plural = 'Diários de Classe'
        ordering = ['-data', 'turma__nome']
        constraints = [
            models.UniqueConstraint(
                fields=['turma', 'data', 'turno'],
                name='unique_diario_turma_data_turno'
            )
        ]
        indexes = [
            models.Index(fields=['data', 'turma']),
        ]

    def __str__(self):
        return f"Diário {self.turma.nome} - {self.data.strftime('%d/%m/%Y')} ({self.get_turno_display()})"

    @property
    def total_alunos(self):
        return self.registros.count()

    @property
    def total_presentes(self):
        return self.registros.filter(status=StatusPresenca.PRESENTE).count()

    @property
    def total_faltas(self):
        return self.registros.filter(status=StatusPresenca.AUSENTE).count()

    @property
    def total_justificadas(self):
        return self.registros.filter(status=StatusPresenca.JUSTIFICADO).count()


# Mantendo alias LancamentoChamada para total retrocompatibilidade
LancamentoChamada = DiarioDeClasse


class RegistroPresenca(models.Model):
    diario_classe = models.ForeignKey(
        DiarioDeClasse,
        on_delete=models.CASCADE,
        related_name='registros',
        null=True,
        blank=True,
        verbose_name='Diário de Classe'
    )
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.PROTECT,
        related_name='presencas',
        verbose_name='Aluno'
    )
    turma = models.ForeignKey(
        Turma,
        on_delete=models.PROTECT,
        related_name='registros_presenca',
        verbose_name='Turma'
    )
    data = models.DateField(default=timezone.now, verbose_name='Data')
    status = models.CharField(
        max_length=20,
        choices=StatusPresenca.choices,
        default=StatusPresenca.PRESENTE,
        verbose_name='Status'
    )
    observacao = models.TextField(blank=True, verbose_name='Observação / Justificativa')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Registrado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registro de Presença'
        verbose_name_plural = 'Registros de Presença'
        ordering = ['-data', 'aluno__nome']
        constraints = [
            models.UniqueConstraint(fields=['aluno', 'data'], name='unique_registro_aluno_data')
        ]
        indexes = [
            models.Index(fields=['data', 'turma']),
            models.Index(fields=['aluno', 'status']),
            models.Index(fields=['status', 'data']),
        ]

    def __str__(self):
        return f"{self.aluno.nome} - {self.data.strftime('%d/%m/%Y')} ({self.get_status_display()})"


# ==============================================================================
# SIGNAL: Automação do Pré-Preenchimento Rápido com bulk_create
# ==============================================================================
@receiver(post_save, sender=DiarioDeClasse)
def auto_popular_presencas_diario(sender, instance, created, **kwargs):
    """
    Ao criar uma nova sessão de diário de classe, gera em lote os registros de
    presença pré-preenchidos com 'PRESENTE' para todos os alunos ativos da turma.
    """
    if created:
        alunos_qs = instance.turma.alunos.filter(ativo=True)
        if instance.turno != TurnoFiltro.TODOS:
            if instance.turno == TurnoAluno.MATUTINO:
                alunos_qs = alunos_qs.filter(Q(turno=TurnoAluno.MATUTINO) | Q(turno=TurnoAluno.INTEGRAL))
            elif instance.turno == TurnoAluno.VESPERTINO:
                alunos_qs = alunos_qs.filter(Q(turno=TurnoAluno.VESPERTINO) | Q(turno=TurnoAluno.INTEGRAL))
            else:
                alunos_qs = alunos_qs.filter(turno=instance.turno)

        # Evita duplicar se já existirem registros para essa data/aluno
        alunos_existentes_ids = set(
            RegistroPresenca.objects.filter(
                data=instance.data,
                aluno__in=alunos_qs
            ).values_list('aluno_id', flat=True)
        )

        novos_registros = [
            RegistroPresenca(
                diario_classe=instance,
                turma=instance.turma,
                aluno=aluno,
                data=instance.data,
                status=StatusPresenca.PRESENTE,
                registrado_por=instance.registrado_por
            )
            for aluno in alunos_qs if aluno.id not in alunos_existentes_ids
        ]

        if novos_registros:
            with transaction.atomic():
                RegistroPresenca.objects.bulk_create(novos_registros)


class TipoOcorrencia(models.TextChoices):
    FALTA = 'falta', 'Falta'
    ATESTADO = 'atestado', 'Atestado Médico'
    ATRASO = 'atraso', 'Atraso'
    SAIDA = 'saida', 'Saída Antecipada'
    AMAMENTACAO = 'amamentacao', 'Amamentação'


class OcorrenciaCaderno(models.Model):
    """
    Entidade do Módulo II: Caderno SEAMI (Gestão de Imprevistos e Ocorrências).
    Armazena Faltas, Atestados Médicos, Atrasos, Saídas Antecipadas e Amamentação.
    """
    tipo = models.CharField(
        max_length=20,
        choices=TipoOcorrencia.choices,
        verbose_name='Tipo de Ocorrência'
    )
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.CASCADE,
        related_name='ocorrencias_caderno',
        null=True,
        blank=True,
        verbose_name='Aluno / Criança'
    )
    turma = models.ForeignKey(
        Turma,
        on_delete=models.SET_NULL,
        related_name='ocorrencias_caderno',
        null=True,
        blank=True,
        verbose_name='Sala / Turma'
    )
    data = models.DateField(default=timezone.now, verbose_name='Data do Evento')
    data_fim = models.DateField(null=True, blank=True, verbose_name='Data de Término do Afastamento')
    horario = models.TimeField(null=True, blank=True, verbose_name='Horário do Evento')
    horario_retorno = models.TimeField(null=True, blank=True, verbose_name='Horário Previsto de Retorno')
    retorna = models.BooleanField(default=False, verbose_name='Retorna no mesmo dia?')
    justificado = models.BooleanField(default=False, verbose_name='Justificado?')
    avisado_pais = models.BooleanField(default=False, verbose_name='Avisado previamente pelos pais?')
    cid = models.CharField(max_length=50, blank=True, verbose_name='CID (Classificação Internacional de Doenças)')
    motivo = models.TextField(blank=True, verbose_name='Motivo Declarado')
    quantidade = models.CharField(max_length=50, blank=True, verbose_name='Quantidade / Sessão / Duração')
    observacao = models.TextField(blank=True, verbose_name='Observações Adicionais')
    documento = models.FileField(upload_to='caderno_docs/%Y/%m/', null=True, blank=True, verbose_name='Documento / Atestado Anexo')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Registrado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ocorrência do Caderno SEAMI'
        verbose_name_plural = 'Ocorrências do Caderno SEAMI'
        ordering = ['-data', '-criado_em']

    def __str__(self):
        nome = self.aluno.nome if self.aluno else "Amamentação Geral"
        return f"[{self.get_tipo_display()}] {nome} - {self.data.strftime('%d/%m/%Y')}"

    @property
    def periodo_formatado(self):
        """Retorna texto amigável de período (ex: '2 dias (13/08/2026 a 14/08/2026)')"""
        if not self.data_fim or self.data_fim == self.data:
            return f"1 dia ({self.data.strftime('%d/%m/%Y')})"
        diff_dias = (self.data_fim - self.data).days + 1
        return f"{diff_dias} dias ({self.data.strftime('%d/%m/%Y')} a {self.data_fim.strftime('%d/%m/%Y')})"


@receiver([post_save, post_delete], sender=Aluno)
def atualizar_cache_headcount_alunos(sender, instance, **kwargs):
    """
    Sempre que um aluno for cadastrado, editado, desativado ou excluído,
    recalcula e atualiza automaticamente o arquivo JSON de headcount de matrículas.
    """
    try:
        from .services import calcular_e_salvar_matriculados_headcount
        calcular_e_salvar_matriculados_headcount()
    except Exception as e:
        pass
