from datetime import date, timedelta
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.db.models import Count, Q


def extrair_nome_usuario(user):
    """Retorna o nome completo ou username de um objeto User."""
    if not user:
        return ''
    return (user.get_full_name() or user.username or '').strip()


def obter_responsavel_enfermaria(user_fallback=None, nome_fallback=''):
    """
    Retorna a tupla (user_obj_ou_None, nome_em_texto) vinculada estritamente à FK
    do usuário que realizou o registro na Enfermaria.
    """
    if user_fallback and getattr(user_fallback, 'pk', None):
        return user_fallback, extrair_nome_usuario(user_fallback)

    return None, ''


def is_ocorrencia_enfermaria(oc):
    """Verifica se uma OcorrenciaCaderno teve origem na Enfermaria."""
    if not oc:
        return False
    texto = f"{oc.motivo or ''} {oc.observacao or ''}".lower()
    return any(termo in texto for termo in ['enfermagem', 'enfermaria', 'afastamento médico'])


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
        related_name='turmas_como_professor',
        blank=True,
        verbose_name='Professores Responsáveis'
    )
    auxiliares = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='turmas_como_auxiliar',
        blank=True,
        verbose_name='Auxiliares da Turma'
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

    def get_professores_display(self):
        profs = [p.get_full_name() or p.username for p in self.professores.all()]
        return ", ".join(profs) if profs else "Nenhum professor vinculado"

    def get_auxiliares_display(self):
        auxs = [a.get_full_name() or a.username for a in self.auxiliares.all()]
        return ", ".join(auxs) if auxs else "Nenhum auxiliar vinculado"


class Orgao(models.Model):
    """
    Representa o Órgão Central mantenedor ao qual a creche pertence (MS - Ministério da Saúde)
    e os demais órgãos públicos e instituições conveniadas por contrato
    através dos quais as crianças e seus responsáveis são atendidos no SEAMI.
    """
    nome = models.CharField(max_length=150, unique=True, verbose_name='Nome do Órgão / Instituição')
    sigla = models.CharField(max_length=30, blank=True, default='', verbose_name='Sigla')
    descricao = models.TextField(blank=True, default='', verbose_name='Descrição / Contrato')
    is_central = models.BooleanField(default=False, verbose_name='Órgão Central (Mantenedor)')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Órgão (Central / Conveniado)'
        verbose_name_plural = 'Órgãos (Central e Conveniados)'
        ordering = ['-is_central', 'nome']

    @property
    def tipo_vinculo_label(self):
        return 'Órgão Central' if self.is_central else 'Órgão Conveniado'

    def save(self, *args, **kwargs):
        sigla_upper = (self.sigla or '').strip().upper()
        nome_lower = (self.nome or '').strip().lower()
        if self.pk is None and (sigla_upper == 'MS' or 'ministério da saúde' in nome_lower or 'ministerio da saude' in nome_lower):
            self.is_central = True

        super().save(*args, **kwargs)

        if self.is_central:
            Orgao.objects.exclude(pk=self.pk).filter(is_central=True).update(is_central=False)

    def __str__(self):
        sufixo = " (Órgão Central)" if self.is_central else ""
        if self.sigla:
            return f"{self.sigla} - {self.nome}{sufixo}"
        return f"{self.nome}{sufixo}"


class StatusRecebimentoAcordo(models.TextChoices):
    AGUARDANDO = 'aguardando', 'Aguardando recebimento'
    RECEBIDO = 'recebido', 'Recebido'


class ItemAcordoOrgao(models.Model):
    """
    Itens vinculados a um Órgão Conveniado que serão recebidos em cumprimento
    de acordo, com controle individual de status de recebimento
    ('Aguardando recebimento' ou 'Recebido').
    """
    orgao = models.ForeignKey(
        Orgao,
        on_delete=models.CASCADE,
        related_name='itens_acordo',
        verbose_name='Órgão Conveniado'
    )
    descricao = models.CharField(
        max_length=255,
        verbose_name='Item / Descrição do Acordo'
    )
    quantidade = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Quantidade / Especificação'
    )
    status = models.CharField(
        max_length=25,
        choices=StatusRecebimentoAcordo.choices,
        default=StatusRecebimentoAcordo.AGUARDANDO,
        verbose_name='Status de Recebimento'
    )
    data_recebimento = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Recebimento'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Item de Acordo do Órgão'
        verbose_name_plural = 'Itens de Acordo dos Órgãos'
        ordering = ['id']

    def __str__(self):
        qtd_str = f" ({self.quantidade})" if self.quantidade else ""
        return f"{self.orgao} — {self.descricao}{qtd_str} [{self.get_status_display()}]"


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
    orgao = models.ForeignKey(
        Orgao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alunos',
        verbose_name='Órgão do Aluno (Contrato)'
    )
    data_entrada = models.DateField(null=True, blank=True, verbose_name='Data de Entrada')
    data_desligamento = models.DateField(null=True, blank=True, verbose_name='Data de Desligamento')
    motivo_desligamento = models.TextField(blank=True, verbose_name='Motivo do Desligamento')
    has_acompanhamento = models.BooleanField(default=False, verbose_name='Possui Acompanhamento Especial')
    acompanhamento_obs = models.TextField(blank=True, verbose_name='Observações de Acompanhamento')
    acompanhamento_dias = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Dias e Horários de Acompanhamento',
        help_text='Dias e horários de acompanhamento. Ex: Ter 15:00, Qui 16:00'
    )
    alergias = models.TextField(blank=True, default='', verbose_name='Alergias')
    restricoes_alimentares = models.TextField(blank=True, default='', verbose_name='Restrições Alimentares')
    comorbidades = models.TextField(blank=True, default='', verbose_name='Comorbidades / Condições de Saúde')
    nome_responsavel = models.CharField(max_length=150, blank=True, verbose_name='Nome do Responsável')
    telefone_responsavel = models.CharField(max_length=20, blank=True, verbose_name='Telefone do Responsável')
    email_responsavel = models.EmailField(blank=True, verbose_name='E-mail do Responsável')
    orgao_responsavel = models.ForeignKey(
        Orgao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alunos_responsavel_1',
        verbose_name='Órgão do Responsável Principal'
    )
    nome_responsavel_2 = models.CharField(max_length=150, blank=True, verbose_name='Nome do 2º Responsável')
    telefone_responsavel_2 = models.CharField(max_length=20, blank=True, verbose_name='Telefone do 2º Responsável')
    email_responsavel_2 = models.EmailField(blank=True, verbose_name='E-mail do 2º Responsável')
    orgao_responsavel_2 = models.ForeignKey(
        Orgao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alunos_responsavel_2',
        verbose_name='Órgão do 2º Responsável'
    )
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
            models.Index(fields=['orgao']),
            models.Index(fields=['orgao_responsavel']),
        ]

    def __str__(self):
        return f"{self.nome} - Sala {self.turma.nome}"

    def save(self, *args, **kwargs):
        today = timezone.localdate()
        is_new = self.pk is None
        old_obj = None
        if not is_new:
            old_obj = Aluno.objects.select_related('turma').filter(pk=self.pk).first()

        if self.data_desligamento:
            if self.data_desligamento <= today:
                self.ativo = False
            else:
                self.ativo = True  # Permanece ativo até a data da saída futura
        elif not self.ativo and not self.data_desligamento:
            self.data_desligamento = today

        # A criança reflete automaticamente o órgão do responsável principal (contrato de convênio)
        if self.orgao_responsavel:
            self.orgao = self.orgao_responsavel
        elif not self.orgao_responsavel and self.orgao:
            self.orgao_responsavel = self.orgao

        super().save(*args, **kwargs)

        if getattr(self, '_skip_auto_historico', False):
            return

        # Registro automático de observabilidade de realocação de Turma (Sala) e Turno
        try:
            curr_turma_nome = self.turma.nome if self.turma_id else ''
            data_realocacao = getattr(self, '_data_realocacao', None) or today
            obs_realocacao = getattr(self, '_obs_realocacao', '') or ''

            if is_new:
                HistoricoAlocacaoAluno.objects.create(
                    aluno=self,
                    turma=self.turma if self.turma_id else None,
                    turma_nome=curr_turma_nome,
                    turno=self.turno,
                    data_inicio=self.data_entrada or today,
                    data_fim=self.data_desligamento,
                    observacao='Alocação inicial',
                )
            elif old_obj is not None:
                mudou_turma = old_obj.turma_id != self.turma_id
                mudou_turno = old_obj.turno != self.turno
                if mudou_turma or mudou_turno:
                    if not self.historico_alocacoes.exists():
                        old_inicio = old_obj.data_entrada or (old_obj.criado_em.date() if old_obj.criado_em else today)
                        old_turma_nome = old_obj.turma.nome if old_obj.turma_id else ''
                        HistoricoAlocacaoAluno.objects.create(
                            aluno=self,
                            turma=old_obj.turma if old_obj.turma_id else None,
                            turma_nome=old_turma_nome,
                            turno=old_obj.turno,
                            data_inicio=old_inicio,
                            data_fim=data_realocacao,
                            observacao='Alocação anterior',
                        )
                    else:
                        self.historico_alocacoes.filter(data_fim__isnull=True).update(data_fim=data_realocacao)

                    if not obs_realocacao:
                        old_turma_nome = old_obj.turma.nome if old_obj.turma_id else ''
                        if mudou_turma and mudou_turno:
                            obs_realocacao = f"Realocação: Sala {old_turma_nome} ({old_obj.get_turno_display()}) → Sala {curr_turma_nome} ({self.get_turno_display()})"
                        elif mudou_turma:
                            obs_realocacao = f"Mudança de sala: Sala {old_turma_nome} → Sala {curr_turma_nome}"
                        else:
                            obs_realocacao = f"Mudança de turno: {old_obj.get_turno_display()} → {self.get_turno_display()}"

                    HistoricoAlocacaoAluno.objects.create(
                        aluno=self,
                        turma=self.turma if self.turma_id else None,
                        turma_nome=curr_turma_nome,
                        turno=self.turno,
                        data_inicio=data_realocacao,
                        data_fim=self.data_desligamento,
                        observacao=obs_realocacao,
                    )
                else:
                    # Sincroniza data_entrada na alocação inicial caso só exista 1 registro
                    if self.data_entrada and self.historico_alocacoes.count() == 1:
                        unico = self.historico_alocacoes.first()
                        if unico and unico.observacao in ('Alocação inicial', 'Alocação atual', ''):
                            unico.data_inicio = self.data_entrada
                            unico.data_fim = self.data_desligamento
                            unico.save(update_fields=['data_inicio', 'data_fim'])
        except Exception:
            pass

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

    @property
    def is_orgao_central(self):
        """Retorna True se o órgão da criança/contrato for o Órgão Central (MS)."""
        org = self.orgao or self.orgao_responsavel
        return bool(org and getattr(org, 'is_central', False))

    @property
    def orgao_display(self):
        """Retorna o nome ou sigla do órgão da criança (Central ou Conveniado)."""
        if self.orgao:
            return self.orgao.sigla or self.orgao.nome
        if self.orgao_responsavel:
            return self.orgao_responsavel.sigla or self.orgao_responsavel.nome
        return "Não informado"

    @property
    def orgao_responsavel_display(self):
        """Retorna o nome ou sigla do órgão de lotação do 1º responsável."""
        if self.orgao_responsavel:
            return self.orgao_responsavel.sigla or self.orgao_responsavel.nome
        return "Não informado"

    @property
    def orgao_responsavel_2_display(self):
        """Retorna o nome ou sigla do órgão de lotação do 2º responsável."""
        if self.orgao_responsavel_2:
            return self.orgao_responsavel_2.sigla or self.orgao_responsavel_2.nome
        return ""

    @property
    def idade_extenso(self):
        """Retorna a idade atual formatada (anos e meses)."""
        if not self.data_nascimento:
            return ""
        today = timezone.localdate()
        if self.data_nascimento > today:
            return ""

        years = today.year - self.data_nascimento.year
        months = today.month - self.data_nascimento.month
        days = today.day - self.data_nascimento.day

        if days < 0:
            months -= 1
        if months < 0:
            years -= 1
            months += 12

        if years == 0:
            if months == 0:
                diff_days = (today - self.data_nascimento).days
                if diff_days <= 1:
                    return "Recém-nascido"
                return f"{diff_days} dias"
            elif months == 1:
                return "1 mês"
            else:
                return f"{months} meses"
        elif years == 1:
            if months == 0:
                return "1 ano"
            elif months == 1:
                return "1 ano e 1 mês"
            else:
                return f"1 ano e {months} meses"
        else:
            if months == 0:
                return f"{years} anos"
            elif months == 1:
                return f"{years} anos e 1 mês"
            else:
                return f"{years} anos e {months} meses"

    @property
    def is_aniversariante_hoje(self):
        """Retorna True se hoje for a data de aniversário da criança."""
        if not self.data_nascimento:
            return False
        today = timezone.localdate()
        return self.data_nascimento.day == today.day and self.data_nascimento.month == today.month

    def obter_periodos_turma_e_turno(self):
        """
        Retorna os períodos de permanência da criança em cada Turma (Sala) e em cada Turno.
        Por default, caso não haja histórico de realocação registrado, retorna a Turma atual
        e o Turno atual (a partir da data de entrada ou criação até 'Atual').
        """
        default_inicio = self.data_entrada or (self.criado_em.date() if self.criado_em else None)
        default_inicio_br = default_inicio.strftime('%d/%m/%Y') if default_inicio else 'Desde o ingresso'
        default_fim_br = self.data_desligamento.strftime('%d/%m/%Y') if self.data_desligamento else 'Atual'
        curr_turma_nome = self.turma.nome if self.turma_id else ''
        curr_turno_display = self.get_turno_display()

        registros = []
        try:
            registros = list(self.historico_alocacoes.all())
        except Exception:
            registros = []

        if not registros:
            return {
                'periodos_turma': [{
                    'turma_nome': curr_turma_nome,
                    'data_inicio_br': default_inicio_br,
                    'data_fim_br': default_fim_br,
                    'periodo_str': f"{default_inicio_br} — {default_fim_br}",
                    'atual': True,
                    'observacao': 'Sala atual',
                }],
                'periodos_turno': [{
                    'turno': self.turno,
                    'turno_display': curr_turno_display,
                    'data_inicio_br': default_inicio_br,
                    'data_fim_br': default_fim_br,
                    'periodo_str': f"{default_inicio_br} — {default_fim_br}",
                    'atual': True,
                    'observacao': 'Turno atual',
                }],
                'historico_raw': [{
                    'id': '',
                    'turma_id': self.turma_id or '',
                    'turma_nome': curr_turma_nome,
                    'turno': (self.turno or 'integral').lower(),
                    'turno_display': curr_turno_display,
                    'data_inicio': default_inicio.isoformat() if default_inicio else '',
                    'data_inicio_br': default_inicio_br,
                    'data_fim': self.data_desligamento.isoformat() if self.data_desligamento else '',
                    'data_fim_br': default_fim_br,
                    'observacao': 'Alocação inicial',
                    'atual': True,
                }],
            }

        # Ordena cronologicamente (do mais antigo para o mais recente)
        registros_sorted = sorted(
            registros,
            key=lambda r: (r.data_inicio.isoformat() if r.data_inicio else '0000-00-00', r.id or 0)
        )

        historico_raw = []
        for idx, reg in enumerate(registros_sorted):
            t_nome = reg.turma.nome if reg.turma_id and reg.turma else (reg.turma_nome or curr_turma_nome)
            ini_br = reg.data_inicio.strftime('%d/%m/%Y') if reg.data_inicio else default_inicio_br
            fim_br = reg.data_fim.strftime('%d/%m/%Y') if reg.data_fim else default_fim_br
            is_last = (idx == len(registros_sorted) - 1)
            historico_raw.append({
                'id': reg.id,
                'turma_id': reg.turma_id or self.turma_id or '',
                'turma_nome': t_nome,
                'turno': (reg.turno or self.turno or 'integral').lower(),
                'turno_display': reg.get_turno_display() if reg.turno else curr_turno_display,
                'data_inicio': reg.data_inicio.isoformat() if reg.data_inicio else (default_inicio.isoformat() if default_inicio else ''),
                'data_inicio_br': ini_br,
                'data_fim': reg.data_fim.isoformat() if reg.data_fim else '',
                'data_fim_br': fim_br,
                'observacao': reg.observacao or '',
                'atual': is_last or (reg.data_fim is None),
            })

        # 1. Consolida períodos consecutivos na mesma Turma (Sala)
        periodos_turma = []
        for idx, reg in enumerate(registros_sorted):
            t_nome = reg.turma.nome if reg.turma_id and reg.turma else (reg.turma_nome or curr_turma_nome)
            ini_br = reg.data_inicio.strftime('%d/%m/%Y') if reg.data_inicio else default_inicio_br
            fim_br = reg.data_fim.strftime('%d/%m/%Y') if reg.data_fim else default_fim_br
            is_last = (idx == len(registros_sorted) - 1)
            is_atual = is_last or (reg.data_fim is None)

            if periodos_turma and periodos_turma[-1]['turma_nome'] == t_nome:
                # Continua na mesma sala (mudou apenas turno): estende o término
                periodos_turma[-1]['data_fim_br'] = fim_br
                periodos_turma[-1]['periodo_str'] = f"{periodos_turma[-1]['data_inicio_br']} — {fim_br}"
                periodos_turma[-1]['atual'] = is_atual
            else:
                periodos_turma.append({
                    'turma_nome': t_nome,
                    'data_inicio_br': ini_br,
                    'data_fim_br': fim_br,
                    'periodo_str': f"{ini_br} — {fim_br}",
                    'atual': is_atual,
                    'observacao': reg.observacao or '',
                })

        # Garante que apenas o último período de turma esteja marcado como atual (ou sincronizado com a sala atual)
        for i, p in enumerate(periodos_turma):
            p['atual'] = (i == len(periodos_turma) - 1)
            if p['atual'] and not self.data_desligamento:
                p['data_fim_br'] = 'Atual'
                p['periodo_str'] = f"{p['data_inicio_br']} — Atual"

        # 2. Consolida períodos consecutivos no mesmo Turno
        periodos_turno = []
        for idx, reg in enumerate(registros_sorted):
            t_code = reg.turno or self.turno
            t_disp = reg.get_turno_display() if reg.turno else curr_turno_display
            ini_br = reg.data_inicio.strftime('%d/%m/%Y') if reg.data_inicio else default_inicio_br
            fim_br = reg.data_fim.strftime('%d/%m/%Y') if reg.data_fim else default_fim_br
            is_last = (idx == len(registros_sorted) - 1)
            is_atual = is_last or (reg.data_fim is None)

            if periodos_turno and periodos_turno[-1]['turno'] == t_code:
                # Continua no mesmo turno (mudou apenas sala): estende o término
                periodos_turno[-1]['data_fim_br'] = fim_br
                periodos_turno[-1]['periodo_str'] = f"{periodos_turno[-1]['data_inicio_br']} — {fim_br}"
                periodos_turno[-1]['atual'] = is_atual
            else:
                periodos_turno.append({
                    'turno': t_code,
                    'turno_display': t_disp,
                    'data_inicio_br': ini_br,
                    'data_fim_br': fim_br,
                    'periodo_str': f"{ini_br} — {fim_br}",
                    'atual': is_atual,
                    'observacao': reg.observacao or '',
                })

        for i, p in enumerate(periodos_turno):
            p['atual'] = (i == len(periodos_turno) - 1)
            if p['atual'] and not self.data_desligamento:
                p['data_fim_br'] = 'Atual'
                p['periodo_str'] = f"{p['data_inicio_br']} — Atual"

        return {
            'periodos_turma': periodos_turma,
            'periodos_turno': periodos_turno,
            'historico_raw': historico_raw,
        }


class HistoricoAlocacaoAluno(models.Model):
    """
    Registra o histórico de alocação e realocação de Turma (Sala) e Turno de cada criança,
    permitindo observabilidade completa do período em cada turma e em cada turno.
    """
    aluno = models.ForeignKey(
        Aluno,
        on_delete=models.CASCADE,
        related_name='historico_alocacoes',
        verbose_name='Criança / Aluno'
    )
    turma = models.ForeignKey(
        Turma,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historico_alocacoes',
        verbose_name='Turma / Sala'
    )
    turma_nome = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Nome da Sala (Snapshot)'
    )
    turno = models.CharField(
        max_length=20,
        choices=TurnoAluno.choices,
        default=TurnoAluno.INTEGRAL,
        verbose_name='Turno'
    )
    data_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Início'
    )
    data_fim = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Término',
        help_text='Vazio indica que é a alocação atual da criança.'
    )
    observacao = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Observação / Motivo da Realocação'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Alocação (Turma/Turno)'
        verbose_name_plural = 'Históricos de Alocação (Turma/Turno)'
        ordering = ['data_inicio', 'id']
        indexes = [
            models.Index(fields=['aluno', 'data_inicio']),
        ]

    def __str__(self):
        fim = self.data_fim.strftime('%d/%m/%Y') if self.data_fim else 'Atual'
        ini = self.data_inicio.strftime('%d/%m/%Y') if self.data_inicio else 'Ingresso'
        sala = self.turma.nome if self.turma_id and self.turma else self.turma_nome
        return f"{self.aluno.nome} — Sala {sala} ({self.get_turno_display()}): {ini} a {fim}"


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
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
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
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

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
    
    status_chamada = models.CharField(
        max_length=20,
        choices=StatusPresenca.choices,
        default=StatusPresenca.PRESENTE,
        verbose_name='Status Base da Chamada'
    )
    observacao = models.TextField(blank=True, verbose_name='Observação / Evidência')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Registrado por'
    )
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
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

    @property
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

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

        # Busca ocorrências ativas no Caderno SEAMI para esta data
        ocorrs_map = {}
        for oc in OcorrenciaCaderno.objects.filter(
            tipo__in=[TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]
        ).filter(
            Q(data=instance.data, data_fim__isnull=True) |
            Q(data=instance.data, data_fim=instance.data) |
            Q(data__lte=instance.data, data_fim__gte=instance.data)
        ):
            if oc.aluno_id:
                if oc.aluno_id not in ocorrs_map:
                    ocorrs_map[oc.aluno_id] = oc
                elif oc.tipo == TipoOcorrencia.ATESTADO or oc.justificado:
                    ocorrs_map[oc.aluno_id] = oc

        novos_registros = []
        for aluno in alunos_qs:
            if aluno.id in alunos_existentes_ids:
                continue

            oc = ocorrs_map.get(aluno.id)
            if oc and (oc.justificado or oc.tipo == TipoOcorrencia.ATESTADO):
                st_base = StatusPresenca.JUSTIFICADO
                st_turno_base = StatusTurnoPresenca.JUSTIFICADO
                obs_extra = oc.motivo or oc.observacao or ('Atestado médico' if oc.tipo == TipoOcorrencia.ATESTADO else 'Falta Justificada')
            elif oc and oc.tipo == TipoOcorrencia.FALTA:
                st_base = StatusPresenca.AUSENTE
                st_turno_base = StatusTurnoPresenca.AUSENTE
                obs_extra = oc.motivo or oc.observacao or 'Falta'
            else:
                st_base = StatusPresenca.PRESENTE
                st_turno_base = StatusTurnoPresenca.PRESENTE
                obs_extra = None

            turno_aluno = (aluno.turno or 'integral').lower()
            if turno_aluno == 'matutino':
                sm = st_turno_base
                sv = StatusTurnoPresenca.NA
            elif turno_aluno == 'vespertino':
                sm = StatusTurnoPresenca.NA
                sv = st_turno_base
            else:
                sm = st_turno_base
                sv = st_turno_base

            if oc and is_ocorrencia_enfermaria(oc):
                reg_user, reg_nome = obter_responsavel_enfermaria(oc.registrado_por, oc.registrado_por_nome)
            elif oc and (oc.registrado_por_id or oc.registrado_por_nome):
                reg_user = oc.registrado_por
                reg_nome = oc.registrado_por_display
            else:
                reg_user = instance.registrado_por
                reg_nome = instance.registrado_por_display

            reg = RegistroPresenca(
                diario_classe=instance,
                turma=instance.turma,
                aluno=aluno,
                data=instance.data,
                status=st_base,
                status_matutino=sm,
                status_vespertino=sv,
                status_chamada=st_base,
                registrado_por=reg_user,
                registrado_por_nome=reg_nome
            )
            reg.calcular_status_e_observacao(custom_obs=obs_extra)
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
    EXTRACAO = 'extracao', 'Sala de Extração'


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
        related_name='ocorrencias_caderno_registradas',
        verbose_name='Registrado por'
    )
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ocorrencias_caderno_modificadas',
        verbose_name='Última modificação por'
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
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

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
        related_name='amamentacoes_registradas',
        verbose_name='Registrado por'
    )
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='amamentacoes_modificadas',
        verbose_name='Última modificação por'
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

    @property
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.data:
            self.ano = self.data.year
            self.mes = self.data.month
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Amamentação {self.data.strftime('%d/%m/%Y')} - {self.quantidade} utilizações"


class RegistroExtracao(models.Model):
    """
    Registro diário de utilização da Sala de Extração e Armazenamento de Leite Materno
    (Espaço Materno - Série Histórica e Montantes Mensais/Anuais).
    """
    data = models.DateField(unique=True, verbose_name='Data de Utilização')
    quantidade = models.PositiveIntegerField(default=1, verbose_name='Quantidade de Utilizações da Sala no Dia')
    ano = models.IntegerField(verbose_name='Ano', db_index=True)
    mes = models.IntegerField(verbose_name='Mês', db_index=True)
    observacao = models.TextField(blank=True, verbose_name='Observações')

    anexo = models.FileField(
        upload_to='attachments/extracao/',
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
        related_name='extracoes_registradas',
        verbose_name='Registrado por'
    )
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='extracoes_modificadas',
        verbose_name='Última modificação por'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registro da Sala de Extração'
        verbose_name_plural = 'Registros da Sala de Extração (Espaço Materno)'
        ordering = ['-data']
        indexes = [
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['data']),
        ]

    @property
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.data:
            self.ano = self.data.year
            self.mes = self.data.month
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Sala de Extração {self.data.strftime('%d/%m/%Y')} - {self.quantidade} utilizações"


class TipoDiaNaoLetivo(models.TextChoices):
    FERIADO = 'FERIADO', 'Feriado'
    RECESSO = 'RECESSO', 'Recesso Escolar'
    EMENDA = 'EMENDA', 'Emenda / Ponto Facultativo'
    OUTRO = 'OUTRO', 'Outro Dia Não Letivo'


class DiaNaoLetivo(models.Model):
    """
    Representa dias não letivos, feriados ou recessos escolares (incluindo intervalos prolongados).
    Nesses dias, a chamada é dispensada e os alunos não têm presença nem falta.
    """
    data_inicio = models.DateField(verbose_name='Data de Início', db_index=True)
    data_fim = models.DateField(verbose_name='Data de Término', db_index=True)
    tipo = models.CharField(
        max_length=20,
        choices=TipoDiaNaoLetivo.choices,
        default=TipoDiaNaoLetivo.FERIADO,
        verbose_name='Tipo de Não Letivo'
    )
    descricao = models.CharField(
        max_length=200,
        verbose_name='Descrição / Motivo'
    )
    turma = models.ForeignKey(
        Turma,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dias_nao_letivos',
        verbose_name='Turma / Sala (Opcional - em branco para todas)'
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dias_nao_letivos_registrados',
        verbose_name='Registrado por'
    )
    registrado_por_nome = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Registrado por (Nome)'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dia Não Letivo / Feriado'
        verbose_name_plural = 'Dias Não Letivos / Feriados'
        ordering = ['-data_inicio', 'descricao']
        indexes = [
            models.Index(fields=['data_inicio', 'data_fim']),
            models.Index(fields=['tipo']),
        ]

    def __str__(self):
        if self.data_inicio == self.data_fim:
            return f"{self.get_tipo_display()}: {self.descricao} ({self.data_inicio.strftime('%d/%m/%Y')})"
        return f"{self.get_tipo_display()}: {self.descricao} ({self.data_inicio.strftime('%d/%m/%Y')} a {self.data_fim.strftime('%d/%m/%Y')})"

    @property
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por) or self.registrado_por_nome
        return self.registrado_por_nome or ''

    def save(self, *args, **kwargs):
        if self.registrado_por_id and self.registrado_por:
            self.registrado_por_nome = extrair_nome_usuario(self.registrado_por)
        super().save(*args, **kwargs)

    @property
    def is_intervalo(self):
        return bool(self.data_fim and self.data_fim != self.data_inicio)

    @property
    def periodo_formatado(self):
        if not self.data_fim or self.data_fim == self.data_inicio:
            return self.data_inicio.strftime('%d/%m/%Y')
        return f"{self.data_inicio.strftime('%d/%m/%Y')} a {self.data_fim.strftime('%d/%m/%Y')}"


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
        verbose_name = 'Atendimento de Enfermagem'
        verbose_name_plural = 'Atendimentos de Enfermagem'
        ordering = ['-data_atendimento', '-horario', '-id']
        indexes = [
            models.Index(fields=['data_atendimento', 'ativo']),
            models.Index(fields=['aluno', 'ativo']),
        ]

    def __str__(self):
        return f"Atendimento: {self.aluno.nome} - {self.data_atendimento.strftime('%d/%m/%Y')} ({self.motivo})"

    @property
    def registrado_por_display(self):
        if self.registrado_por_id and self.registrado_por:
            return extrair_nome_usuario(self.registrado_por)
        return ''

    def soft_delete(self, user=None):
        self.ativo = False
        self.deletado_em = timezone.now()
        if user:
            self.deletado_por = user
        self.save(update_fields=['ativo', 'deletado_em', 'deletado_por'])

        try:
            from .services import reverter_automacoes_enfermaria
            reverter_automacoes_enfermaria(self)
        except Exception:
            pass


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


def recalcular_presenca_para_data(aluno, target_date):
    """
    Recalcula e sincroniza o status de RegistroPresenca para um aluno em uma data específica,
    levando em consideração as ocorrências ativas do Caderno SEAMI e o status_chamada original.
    """
    if not aluno or not target_date:
        return None

    # Busca ocorrências ativas do Caderno SEAMI (Falta ou Atestado) cobrindo esta data
    ocorrs = OcorrenciaCaderno.objects.filter(
        aluno=aluno,
        tipo__in=[TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]
    ).filter(
        Q(data=target_date, data_fim__isnull=True) |
        Q(data=target_date, data_fim=target_date) |
        Q(data__lte=target_date, data_fim__gte=target_date)
    ).order_by('-criado_em')

    tem_justificada = ocorrs.filter(Q(justificado=True) | Q(tipo=TipoOcorrencia.ATESTADO)).exists()
    tem_falta_comum = ocorrs.filter(tipo=TipoOcorrencia.FALTA, justificado=False).exists()

    reg = RegistroPresenca.objects.filter(aluno=aluno, data=target_date).first()

    # Se não há ocorrências e nem RegistroPresenca, nada a fazer
    if not reg and not ocorrs.exists():
        return None

    # Se não existe RegistroPresenca mas há ocorrência no Caderno, cria
    if not reg:
        reg = RegistroPresenca(
            aluno=aluno,
            turma=aluno.turma,
            data=target_date,
            status_chamada=StatusPresenca.PRESENTE
        )

    turno_aluno = (aluno.turno or 'integral').lower()

    if tem_justificada:
        oc_just = ocorrs.filter(Q(justificado=True) | Q(tipo=TipoOcorrencia.ATESTADO)).first()
        reg.status = StatusPresenca.JUSTIFICADO
        st_turno = StatusTurnoPresenca.JUSTIFICADO
        obs_extra = oc_just.motivo or oc_just.observacao or ''
        if not reg.registrado_por_id and not reg.registrado_por_nome:
            reg.registrado_por = oc_just.registrado_por
            reg.registrado_por_nome = oc_just.registrado_por_display
    elif tem_falta_comum:
        oc_falta = ocorrs.filter(tipo=TipoOcorrencia.FALTA, justificado=False).first()
        reg.status = StatusPresenca.AUSENTE
        st_turno = StatusTurnoPresenca.AUSENTE
        obs_extra = oc_falta.motivo or oc_falta.observacao or ''
        if not reg.registrado_por_id and not reg.registrado_por_nome:
            reg.registrado_por = oc_falta.registrado_por
            reg.registrado_por_nome = oc_falta.registrado_por_display
    else:
        # Nenhuma ocorrência ativa no Caderno SEAMI
        if not reg.diario_classe_id and target_date > timezone.localdate():
            # Se o registro de presença é para data futura e não possui diário de chamada oficial do professor
            # (foi gerado antecipadamente por ocorrência do caderno agora inexistente), remove o registro órfão
            reg.delete()
            return None

        # Reverte para o status_chamada original registrado pelo professor no diário de classe
        base_chamada = reg.status_chamada or StatusPresenca.PRESENTE
        if base_chamada == StatusPresenca.AUSENTE:
            reg.status = StatusPresenca.AUSENTE
            st_turno = StatusTurnoPresenca.AUSENTE
            obs_extra = ''
        elif base_chamada == StatusPresenca.JUSTIFICADO:
            reg.status = StatusPresenca.JUSTIFICADO
            st_turno = StatusTurnoPresenca.JUSTIFICADO
            obs_extra = ''
        else:
            reg.status = StatusPresenca.PRESENTE
            st_turno = StatusTurnoPresenca.PRESENTE
            obs_extra = ''

    if turno_aluno == 'matutino':
        reg.status_matutino = st_turno
        reg.status_vespertino = StatusTurnoPresenca.NA
    elif turno_aluno == 'vespertino':
        reg.status_matutino = StatusTurnoPresenca.NA
        reg.status_vespertino = st_turno
    else:  # integral
        reg.status_matutino = st_turno
        reg.status_vespertino = st_turno

    reg.calcular_status_e_observacao(custom_obs=obs_extra)
    reg.save()
    return reg


@receiver(pre_save, sender=OcorrenciaCaderno)
def capturar_estado_anterior_ocorrencia(sender, instance, **kwargs):
    """
    Captura o estado anterior de uma ocorrência para que, caso haja alteração de datas ou tipo,
    as datas antigas possam ser recalculadas/revertidas.
    """
    if instance.pk:
        try:
            instance._old_instance = OcorrenciaCaderno.objects.get(pk=instance.pk)
        except OcorrenciaCaderno.DoesNotExist:
            instance._old_instance = None
    else:
        instance._old_instance = None


@receiver(post_save, sender=OcorrenciaCaderno)
def sincronizar_ocorrencia_com_presenca(sender, instance, **kwargs):
    """
    Quando uma falta (comum ou justificada) ou atestado é registrado/editado no Caderno SEAMI,
    sincroniza a chamada (RegistroPresenca) de todo o período com o status correspondente.
    """
    if not instance.aluno:
        return

    # Se for alteração de datas ou tipo, recalcula as datas antigas que deixaram de ser cobertas
    old_inst = getattr(instance, '_old_instance', None)
    if old_inst and old_inst.tipo in [TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]:
        old_inicio = old_inst.data
        old_fim = old_inst.data_fim or old_inst.data
        if old_fim < old_inicio:
            old_fim = old_inicio

        cur_d = old_inicio
        while cur_d <= old_fim:
            if cur_d.weekday() < 5:
                recalcular_presenca_para_data(old_inst.aluno, cur_d)
            cur_d += timedelta(days=1)

    if instance.tipo not in [TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]:
        return

    data_inicio = instance.data
    data_fim = instance.data_fim or instance.data
    if data_fim < data_inicio:
        data_fim = data_inicio

    cur_d = data_inicio
    while cur_d <= data_fim:
        if cur_d.weekday() < 5:
            recalcular_presenca_para_data(instance.aluno, cur_d)
        cur_d += timedelta(days=1)


@receiver(post_delete, sender=OcorrenciaCaderno)
def reverter_presenca_ao_excluir_ocorrencia(sender, instance, **kwargs):
    """
    Quando uma ocorrência de Falta ou Atestado for apagada/excluída,
    recalcula a chamada do aluno naquelas datas:
    1. Se houver outra ocorrência justificada restante -> Falta Justificada (FJ).
    2. Se houver outra falta comum restante -> Falta (F).
    3. Se não houver mais nenhuma ocorrência -> Reverte para o status_chamada original
       (FALTA se a chamada original era Falta, ou PRESENTE se a chamada era Presente).
    """
    if not instance.aluno or instance.tipo not in [TipoOcorrencia.FALTA, TipoOcorrencia.ATESTADO]:
        return

    data_inicio = instance.data
    data_fim = instance.data_fim or instance.data
    if data_fim < data_inicio:
        data_fim = data_inicio

    cur_d = data_inicio
    while cur_d <= data_fim:
        if cur_d.weekday() < 5:
            recalcular_presenca_para_data(instance.aluno, cur_d)
        cur_d += timedelta(days=1)


@receiver(post_delete, sender=AtendimentoEnfermaria)
def reverter_ao_excluir_atendimento_enfermaria(sender, instance, **kwargs):
    """
    Ao excluir definitivamente um registro de atendimento de enfermagem,
    reverte as ocorrências no Caderno SEAMI e os status de presença gerados.
    """
    try:
        from .services import reverter_automacoes_enfermaria
        reverter_automacoes_enfermaria(instance)
    except Exception:
        pass


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def preservar_nome_ao_excluir_usuario(sender, instance, **kwargs):
    """
    Antes de excluir um usuário (o que acionará on_delete=models.SET_NULL em registrado_por),
    grava o nome do usuário como texto puro em registrado_por_nome sem relação ao usuário.
    """
    nome_texto = extrair_nome_usuario(instance)
    if not nome_texto:
        return

    for model_cls in (
        DiarioDeClasse,
        RegistroPresenca,
        OcorrenciaCaderno,
        RegistroAmamentacao,
        RegistroExtracao,
        DiaNaoLetivo,
    ):
        model_cls.objects.filter(registrado_por=instance).update(registrado_por_nome=nome_texto)


