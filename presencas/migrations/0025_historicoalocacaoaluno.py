# Generated migration for HistoricoAlocacaoAluno (Observabilidade de Realocação de Turma e Turno)

from django.db import migrations, models
import django.db.models.deletion


def popular_historico_inicial_alunos(apps, schema_editor):
    Aluno = apps.get_model('presencas', 'Aluno')
    HistoricoAlocacaoAluno = apps.get_model('presencas', 'HistoricoAlocacaoAluno')
    novos_registros = []
    for aluno in Aluno.objects.select_related('turma').all():
        if not HistoricoAlocacaoAluno.objects.filter(aluno_id=aluno.id).exists():
            data_ini = aluno.data_entrada
            if not data_ini and aluno.criado_em:
                data_ini = aluno.criado_em.date()
            turma_nome = aluno.turma.nome if aluno.turma_id and aluno.turma else ''
            novos_registros.append(
                HistoricoAlocacaoAluno(
                    aluno_id=aluno.id,
                    turma_id=aluno.turma_id,
                    turma_nome=turma_nome,
                    turno=aluno.turno or 'INTEGRAL',
                    data_inicio=data_ini,
                    data_fim=aluno.data_desligamento,
                    observacao='Alocação inicial',
                )
            )
    if novos_registros:
        HistoricoAlocacaoAluno.objects.bulk_create(novos_registros)


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0024_itemacordoorgao'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricoAlocacaoAluno',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('turma_nome', models.CharField(blank=True, default='', max_length=100, verbose_name='Nome da Sala (Snapshot)')),
                ('turno', models.CharField(choices=[('INTEGRAL', 'Integral'), ('MATUTINO', 'Matutino'), ('VESPERTINO', 'Vespertino')], default='INTEGRAL', max_length=20, verbose_name='Turno')),
                ('data_inicio', models.DateField(blank=True, null=True, verbose_name='Data de Início')),
                ('data_fim', models.DateField(blank=True, help_text='Vazio indica que é a alocação atual da criança.', null=True, verbose_name='Data de Término')),
                ('observacao', models.CharField(blank=True, default='', max_length=255, verbose_name='Observação / Motivo da Realocação')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('aluno', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historico_alocacoes', to='presencas.aluno', verbose_name='Criança / Aluno')),
                ('turma', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='historico_alocacoes', to='presencas.turma', verbose_name='Turma / Sala')),
            ],
            options={
                'verbose_name': 'Histórico de Alocação (Turma/Turno)',
                'verbose_name_plural': 'Históricos de Alocação (Turma/Turno)',
                'ordering': ['data_inicio', 'id'],
                'indexes': [
                    models.Index(fields=['aluno', 'data_inicio'], name='presencas_h_aluno_i_7a3c9e_idx'),
                ],
            },
        ),
        migrations.RunPython(popular_historico_inicial_alunos, migrations.RunPython.noop),
    ]

