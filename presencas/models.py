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
    PARCIAL = 'PARCIAL', 'Presença Parcial'
    RECESSO = 'RECESSO', 'Recesso Escolar (RE)'
    FERIADO = 'FERIADO', 'Feriado (FE)'


class StatusTurnoPresenca(models.TextChoices):
    PRESENTE = 'PRESENTE', 'Presente'
    AUSENTE = 'AUSENTE', 'Falta'
    JUSTIFICADO = 'JUSTIFICADO', 'Falta Justificada'
    PENDENTE = 'PENDENTE', 'Pendente'
    NA = 'NA', 'Não se Aplica'


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
        return self.nome


class AlunoQuerySet(models.QuerySet):
    def ativos(self, target_date=None):
        if target_date is None:
            target_date = timezone.localdate()
        return self.filter(
            models.Q(ativo=True) | models.Q(data_desligamento__gt=target_date)
        ).filter(
            models.Q(data_desligamento__isnull=True) | models.Q(data_desligamento__gt=target_date)
        ).filter(
            models.Q(data_entrada__isnull=True) | models.Q(data_entrada__lte=target_date)
        )


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
    alergias = models.TextField(blank=True, default='', verbose_name='Alergias')
    restricoes_alimentares = models.TextField(blank=True, default='', verbose_name='Restrições Alimentares')
    comorbidades = models.TextField(blank=True, default='', verbose_name='Comorbidades / Condições de Saúde')
    nome_responsavel = models.CharField(max_length=150, blank=True, verbose_name='Nome do Responsável')
    telefone_responsavel = models.CharField(max_length=20, blank=True, verbose_name='Telefone do Responsável')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    criado_em = models.DateTimeField(auto_now_add=True)

    objects = AlunoQuerySet.as_manager()

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

    def save(self, *args, **kwargs):
        today = timezone.localdate()
        if self.data_desligamento:
            if self.data_desligamento <= today:
                self.ativo = False
            else:
                self.ativo = True  # Permanece ativo até a data da saída futura
        elif not self.ativo and not self.data_desligamento:
            self.data_desligamento = today

        super().save(*args, **kwargs)

    @property
    def is_ativo_hoje(self):
        today = timezone.localdate()
        if not self.ativo:
            return False
        if self.data_entrada and self.data_entrada > today:
            return False
        if self.data_desligamento and self.data_desligamento <= today:
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
    
    # Status consolidado e status detalhado por turnos
    status = models.CharField(
        max_length=20,
        choices=StatusPresenca.choices,
        default=StatusPresenca.PRESENTE,
        verbose_name='Status Geral'
    )
    status_matutino = models.CharField(
        max_length=20,
        choices=StatusTurnoPresenca.choices,
        default=StatusTurnoPresenca.PENDENTE,
        verbose_name='Status Matutino'
    )
    status_vespertino = models.CharField(
        max_length=20,
        choices=StatusTurnoPresenca.choices,
        default=StatusTurnoPresenca.PENDENTE,
        verbose_name='Status Vespertino'
    )
    
    observacao = models.TextField(blank=True, verbose_name='Observação / Evidência')
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
            models.Index(fields=['data', 'status_matutino']),
            models.Index(fields=['data', 'status_vespertino']),
        ]

    def __str__(self):
        return f"{self.aluno.nome} - {self.data.strftime('%d/%m/%Y')} ({self.get_status_display()})"

    def calcular_status_e_observacao(self, custom_obs=None):
        """
        Calcula o status consolidado e a observação formatada de evidência por turno:
        Ex: [Presença registrada - Matutino OK - Vespertino OK]
            [Presença registrada - Matutino OK - Vespertino Pendente]
            [Falta - Matutino Falta - Vespertino Falta]
        """
        turno_aluno = (self.aluno.turno or 'integral').lower() if hasattr(self, 'aluno') and self.aluno else 'integral'

        # Aluno de Turno Matutino
        if turno_aluno == 'matutino':
            self.status_vespertino = StatusTurnoPresenca.NA
            if self.status_matutino == StatusTurnoPresenca.PRESENTE:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença registrada - Matutino OK]'
            elif self.status_matutino == StatusTurnoPresenca.JUSTIFICADO:
                self.status = StatusPresenca.JUSTIFICADO
                prefix = '[Falta Justificada - Matutino FJ]'
            elif self.status_matutino == StatusTurnoPresenca.AUSENTE:
                self.status = StatusPresenca.AUSENTE
                prefix = '[Falta - Matutino Falta]'
            else:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença - Matutino Pendente]'

        # Aluno de Turno Vespertino
        elif turno_aluno == 'vespertino':
            self.status_matutino = StatusTurnoPresenca.NA
            if self.status_vespertino == StatusTurnoPresenca.PRESENTE:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença registrada - Vespertino OK]'
            elif self.status_vespertino == StatusTurnoPresenca.JUSTIFICADO:
                self.status = StatusPresenca.JUSTIFICADO
                prefix = '[Falta Justificada - Vespertino FJ]'
            elif self.status_vespertino == StatusTurnoPresenca.AUSENTE:
                self.status = StatusPresenca.AUSENTE
                prefix = '[Falta - Vespertino Falta]'
            else:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença - Vespertino Pendente]'

        # Aluno de Turno Integral
        else:
            m = self.status_matutino
            v = self.status_vespertino

            m_lbl = 'Matutino OK' if m == StatusTurnoPresenca.PRESENTE else ('Matutino FJ' if m == StatusTurnoPresenca.JUSTIFICADO else ('Matutino Falta' if m == StatusTurnoPresenca.AUSENTE else 'Matutino Pendente'))
            v_lbl = 'Vespertino OK' if v == StatusTurnoPresenca.PRESENTE else ('Vespertino FJ' if v == StatusTurnoPresenca.JUSTIFICADO else ('Vespertino Falta' if v == StatusTurnoPresenca.AUSENTE else 'Vespertino Pendente'))

            if m == StatusTurnoPresenca.PRESENTE and v == StatusTurnoPresenca.PRESENTE:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença registrada - Matutino OK - Vespertino OK]'
            elif m == StatusTurnoPresenca.AUSENTE and v == StatusTurnoPresenca.AUSENTE:
                self.status = StatusPresenca.AUSENTE
                prefix = '[Falta - Matutino Falta - Vespertino Falta]'
            elif m == StatusTurnoPresenca.JUSTIFICADO and v == StatusTurnoPresenca.JUSTIFICADO:
                self.status = StatusPresenca.JUSTIFICADO
                prefix = '[Falta Justificada - Matutino FJ - Vespertino FJ]'
            elif m == StatusTurnoPresenca.PRESENTE and v in [StatusTurnoPresenca.AUSENTE, StatusTurnoPresenca.JUSTIFICADO]:
                self.status = StatusPresenca.PARCIAL
                prefix = f'[Presença registrada - {m_lbl} - {v_lbl}]'
            elif v == StatusTurnoPresenca.PRESENTE and m in [StatusTurnoPresenca.AUSENTE, StatusTurnoPresenca.JUSTIFICADO]:
                self.status = StatusPresenca.PARCIAL
                prefix = f'[Presença registrada - {m_lbl} - {v_lbl}]'
            elif m == StatusTurnoPresenca.PRESENTE and v == StatusTurnoPresenca.PENDENTE:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença registrada - Matutino OK - Vespertino Pendente]'
            elif v == StatusTurnoPresenca.PRESENTE and m == StatusTurnoPresenca.PENDENTE:
                self.status = StatusPresenca.PRESENTE
                prefix = '[Presença registrada - Matutino Pendente - Vespertino OK]'
            elif m == StatusTurnoPresenca.JUSTIFICADO or v == StatusTurnoPresenca.JUSTIFICADO:
                self.status = StatusPresenca.JUSTIFICADO
                prefix = f'[Falta Justificada - {m_lbl} - {v_lbl}]'
            else:
                self.status = StatusPresenca.AUSENTE if (m == StatusTurnoPresenca.AUSENTE or v == StatusTurnoPresenca.AUSENTE) else StatusPresenca.PRESENTE
                prefix = f'[{m_lbl} - {v_lbl}]'

        # Adiciona observação extra se houver
        if custom_obs and custom_obs.strip():
            c_obs = custom_obs.strip()
            # Remove prefixo antigo se já continha
            if c_obs.startswith('[') and ']' in c_obs:
                c_obs = c_obs.split(']', 1)[1].strip()
            if c_obs:
                self.observacao = f"{prefix} {c_obs}"
            else:
                self.observacao = prefix
        else:
            self.observacao = prefix

        return self.observacao


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

        novos_registros = []
        for aluno in alunos_qs:
            if aluno.id in alunos_existentes_ids:
                continue
            turno_aluno = (aluno.turno or 'integral').lower()
            if turno_aluno == 'matutino':
                sm = StatusTurnoPresenca.PRESENTE
                sv = StatusTurnoPresenca.NA
            elif turno_aluno == 'vespertino':
                sm = StatusTurnoPresenca.NA
                sv = StatusTurnoPresenca.PRESENTE
            else:
                sm = StatusTurnoPresenca.PRESENTE
                sv = StatusTurnoPresenca.PRESENTE

            reg = RegistroPresenca(
                diario_classe=instance,
                turma=instance.turma,
                aluno=aluno,
                data=instance.data,
                status=StatusPresenca.PRESENTE,
                status_matutino=sm,
                status_vespertino=sv,
                registrado_por=instance.registrado_por
            )
            reg.calcular_status_e_observacao()
            novos_registros.append(reg)

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
    Armazena Faltas, Atestados Médicos, Atrasos e Saídas Antecipadas.
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
    cid = models.CharField(max_length=255, blank=True, verbose_name='CID (Classificação Internacional de Doenças)')
    motivo = models.TextField(blank=True, verbose_name='Motivo Declarado')
    responsavel = models.CharField(max_length=255, blank=True, verbose_name='Responsável / Acompanhante')
    quantidade = models.CharField(max_length=255, blank=True, verbose_name='Quantidade / Sessão / Duração')
    observacao = models.TextField(blank=True, verbose_name='Observações Adicionais')
    documento = models.FileField(
        upload_to='attachments/ocorrencias/',
        max_length=500,
        null=True,
        blank=True,
        verbose_name='Documento / Anexo'
    )
    attachment_name = models.CharField(max_length=500, blank=True, verbose_name='Nome do Arquivo Anexo')
    attachment_type = models.CharField(max_length=255, blank=True, verbose_name='Tipo MIME do Anexo')
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
        nome = self.aluno.nome if self.aluno else "Ocorrência Geral"
        return f"[{self.get_tipo_display()}] {nome} - {self.data.strftime('%d/%m/%Y')}"

    @property
    def periodo_formatado(self):
        """Retorna texto amigável de período (ex: '2 dias (13/08/2026 a 14/08/2026)')"""
        if not self.data_fim or self.data_fim == self.data:
            return f"1 dia ({self.data.strftime('%d/%m/%Y')})"
        return f"{self.data.strftime('%d/%m/%Y')} até {self.data_fim.strftime('%d/%m/%Y')}"


class RegistroAmamentacao(models.Model):
    """
    Registro diário de utilização da Sala de Amamentação (Série Histórica e Montantes Mensais/Anuais).
    """
    data = models.DateField(unique=True, verbose_name='Data de Utilização')
    quantidade = models.PositiveIntegerField(default=1, verbose_name='Quantidade de Utilizações no Dia')
    ano = models.IntegerField(verbose_name='Ano', db_index=True)
    mes = models.IntegerField(verbose_name='Mês', db_index=True)
    observacao = models.TextField(blank=True, verbose_name='Observações')
    
    anexo = models.FileField(
        upload_to='attachments/amamentacao/',
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Arquivo Anexo'
    )
    attachment_name = models.CharField(max_length=500, blank=True, verbose_name='Nome do Arquivo Anexo')
    attachment_type = models.CharField(max_length=255, blank=True, verbose_name='Tipo MIME do Anexo')
    
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
        verbose_name = 'Registro de Amamentação'
        verbose_name_plural = 'Registros de Amamentação (Sala de Apoio)'
        ordering = ['-data']
        indexes = [
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['data']),
        ]

    def save(self, *args, **kwargs):
        if self.data:
            self.ano = self.data.year
            self.mes = self.data.month
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Amamentação {self.data.strftime('%d/%m/%Y')} - {self.quantidade} utilizações"


class HistoricoFrequenciaMensal(models.Model):
    """
    Série Histórica Multiano de Frequência vs Alunos Matriculados (2019 até 2026+).
    Registra os consolidados mensais de matrículas ativas e médias de presença.
    """
    mes_ano = models.CharField(max_length=7, unique=True, verbose_name='Mês/Ano (YYYY-MM)', db_index=True)
    ano = models.IntegerField(verbose_name='Ano', db_index=True)
    mes = models.IntegerField(verbose_name='Mês', db_index=True)
    matriculados = models.PositiveIntegerField(default=0, verbose_name='Total de Alunos Matriculados')
    presentes_media = models.PositiveIntegerField(default=0, verbose_name='Média de Alunos Presentes / Dia')
    ausentes_media = models.PositiveIntegerField(default=0, verbose_name='Média de Alunos Ausentes / Faltas')
    taxa_frequencia = models.FloatField(default=0.0, verbose_name='Taxa de Frequência (%)')
    observacao = models.TextField(blank=True, verbose_name='Observações')
    
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Histórico Mensal de Frequência'
        verbose_name_plural = 'Históricos Mensais de Frequência (2019-2026)'
        ordering = ['-ano', '-mes']
        indexes = [
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['mes_ano']),
        ]

    def save(self, *args, **kwargs):
        if self.mes_ano and '-' in self.mes_ano:
            parts = self.mes_ano.split('-')
            self.ano = int(parts[0])
            self.mes = int(parts[1])
        if self.matriculados > 0:
            self.taxa_frequencia = round((self.presentes_media / self.matriculados) * 100, 1)
            self.ausentes_media = max(0, self.matriculados - self.presentes_media)
        super().save(*args, **kwargs)

    @property
    def mes_formatado(self):
        meses = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        nome_m = meses[self.mes] if 1 <= self.mes <= 12 else str(self.mes)
        return f"{nome_m} / {self.ano}"

    def __str__(self):
        return f"{self.mes_formatado} - Matr: {self.matriculados} | Pres: {self.presentes_media} ({self.taxa_frequencia}%)"


class AtendimentoEnfermariaQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class AtendimentoEnfermaria(models.Model):
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.CASCADE,
        related_name='atendimentos_enfermaria',
        verbose_name='Aluno'
    )
    data_atendimento = models.DateField(default=timezone.now, verbose_name='Data do Atendimento')
    horario = models.TimeField(default=timezone.now, verbose_name='Horário do Atendimento')
    motivo = models.CharField(max_length=150, verbose_name='Motivo Principal')
    motivo_detalhado = models.TextField(blank=True, verbose_name='Detalhamento do Motivo / Outros')
    
    saida_imediata = models.BooleanField(default=False, verbose_name='Saída Imediata (Antecipada)')
    retornara_dia_seguinte = models.BooleanField(default=True, verbose_name='Retornará no Dia Seguinte')
    data_retorno_prevista = models.DateField(null=True, blank=True, verbose_name='Data Prevista de Retorno')
    
    observacoes_medicas = models.TextField(blank=True, verbose_name='Observações Médicas / Conduta')
    cid = models.CharField(max_length=50, blank=True, verbose_name='CID (Classificação de Doenças)')
    documento_anexo = models.FileField(upload_to='enfermaria/anexos/', blank=True, null=True, verbose_name='Documento Anexo / Atestado')
    
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='atendimentos_registrados',
        verbose_name='Registrado por'
    )

    # Soft Delete exclusivo da Enfermaria
    ativo = models.BooleanField(default=True, verbose_name='Registro Ativo')
    deletado_em = models.DateTimeField(null=True, blank=True, verbose_name='Deletado em')
    deletado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='atendimentos_deletados',
        verbose_name='Deletado por'
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = AtendimentoEnfermariaQuerySet.as_manager()

    class Meta:
        verbose_name = 'Atendimento de Enfermaria'
        verbose_name_plural = 'Atendimentos de Enfermaria'
        ordering = ['-data_atendimento', '-horario', '-id']
        indexes = [
            models.Index(fields=['data_atendimento', 'ativo']),
            models.Index(fields=['aluno', 'ativo']),
        ]

    def __str__(self):
        return f"Atendimento: {self.aluno.nome} - {self.data_atendimento.strftime('%d/%m/%Y')} ({self.motivo})"

    def soft_delete(self, user=None):
        self.ativo = False
        self.deletado_em = timezone.now()
        if user:
            self.deletado_por = user
        self.save(update_fields=['ativo', 'deletado_em', 'deletado_por'])


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


@receiver(post_save, sender=OcorrenciaCaderno)
def sincronizar_ocorrencia_com_presenca(sender, instance, **kwargs):
    """
    Quando uma falta é justificada ou um atestado é registrado no Caderno SEAMI,
    localiza a chamada lançada do aluno naquela(s) data(s) e altera de Falta (F / AUSENTE)
    para Falta Justificada (FJ / JUSTIFICADO).
    Se a falta for desjustificada, reverte para Falta (F / AUSENTE).
    """
    if not instance.aluno:
        return

    data_inicio = instance.data
    data_fim = instance.data_fim or instance.data

    if data_inicio and data_fim and data_fim < data_inicio:
        data_fim = data_inicio

    registros = RegistroPresenca.objects.filter(
        aluno=instance.aluno,
        data__gte=data_inicio,
        data__lte=data_fim
    )

    is_justificada = bool(instance.justificado or instance.tipo == TipoOcorrencia.ATESTADO)

    if instance.tipo in [TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]:
        for reg in registros:
            changed = False
            if is_justificada:
                if reg.status == StatusPresenca.AUSENTE:
                    reg.status = StatusPresenca.JUSTIFICADO
                    changed = True
                if reg.status_matutino == StatusTurnoPresenca.AUSENTE:
                    reg.status_matutino = StatusTurnoPresenca.JUSTIFICADO
                    changed = True
                if reg.status_vespertino == StatusTurnoPresenca.AUSENTE:
                    reg.status_vespertino = StatusTurnoPresenca.JUSTIFICADO
                    changed = True
            else:
                if reg.status == StatusPresenca.JUSTIFICADO:
                    reg.status = StatusPresenca.AUSENTE
                    changed = True
                if reg.status_matutino == StatusTurnoPresenca.JUSTIFICADO:
                    reg.status_matutino = StatusTurnoPresenca.AUSENTE
                    changed = True
                if reg.status_vespertino == StatusTurnoPresenca.JUSTIFICADO:
                    reg.status_vespertino = StatusTurnoPresenca.AUSENTE
                    changed = True

            if changed:
                reg.calcular_status_e_observacao(custom_obs=instance.motivo or instance.observacao)
                reg.save(update_fields=['status', 'status_matutino', 'status_vespertino', 'observacao'])


@receiver(post_delete, sender=OcorrenciaCaderno)
def reverter_presenca_ao_excluir_ocorrencia(sender, instance, **kwargs):
    """
    Quando uma ocorrência de Falta Justificada ou Atestado for apagada/excluída,
    o sistema localiza a chamada lançada do aluno naquelas datas e, caso não
    haja outra justificativa cadastrada para o mesmo dia, reverte o status de
    Falta Justificada (FJ / JUSTIFICADO) de volta para Falta comum (F / AUSENTE).
    """
    if not instance.aluno:
        return

    data_inicio = instance.data
    data_fim = instance.data_fim or instance.data

    if data_inicio and data_fim and data_fim < data_inicio:
        data_fim = data_inicio

    if instance.tipo not in [TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]:
        return

    # Registros de presença desse aluno no período da ocorrência excluída
    registros = RegistroPresenca.objects.filter(
        aluno=instance.aluno,
        data__gte=data_inicio,
        data__lte=data_fim
    )

    for reg in registros:
        # Verifica se ainda existe outra ocorrência justificada para este aluno nesta data específica
        outra_justificativa = OcorrenciaCaderno.objects.filter(
            aluno=instance.aluno,
            tipo__in=[TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]
        ).filter(
            Q(data=reg.data) | (Q(data__lte=reg.data) & Q(data_fim__gte=reg.data))
        ).filter(
            Q(justificado=True) | Q(tipo=TipoOcorrencia.ATESTADO)
        ).exclude(id=instance.id).exists()

        if not outra_justificativa:
            changed = False
            if reg.status == StatusPresenca.JUSTIFICADO:
                reg.status = StatusPresenca.AUSENTE
                changed = True
            if reg.status_matutino == StatusTurnoPresenca.JUSTIFICADO:
                reg.status_matutino = StatusTurnoPresenca.AUSENTE
                changed = True
            if reg.status_vespertino == StatusTurnoPresenca.JUSTIFICADO:
                reg.status_vespertino = StatusTurnoPresenca.AUSENTE
                changed = True

            if changed:
                reg.calcular_status_e_observacao()
                reg.save(update_fields=['status', 'status_matutino', 'status_vespertino', 'observacao'])

