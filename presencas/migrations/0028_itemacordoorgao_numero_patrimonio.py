from django.db import migrations, models


def limpar_presencas_em_feriados_existentes(apps, schema_editor):
    """
    Garante que todos os Feriados / Dias Não Letivos já cadastrados no banco
    não possuam registros de presença, falta ou falta justificada de nenhuma criança.
    """
    DiaNaoLetivo = apps.get_model('presencas', 'DiaNaoLetivo')
    RegistroPresenca = apps.get_model('presencas', 'RegistroPresenca')
    DiarioDeClasse = apps.get_model('presencas', 'DiarioDeClasse')

    for fer in DiaNaoLetivo.objects.all():
        regs_qs = RegistroPresenca.objects.filter(
            data__gte=fer.data_inicio,
            data__lte=fer.data_fim
        )
        diarios_qs = DiarioDeClasse.objects.filter(
            data__gte=fer.data_inicio,
            data__lte=fer.data_fim
        )
        if fer.turma_id:
            regs_qs = regs_qs.filter(turma_id=fer.turma_id)
            diarios_qs = diarios_qs.filter(turma_id=fer.turma_id)
        regs_qs.delete()
        diarios_qs.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0027_orgao_is_central'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemacordoorgao',
            name='numero_patrimonio',
            field=models.CharField(
                blank=True,
                default='',
                max_length=120,
                verbose_name='Número de Patrimônio / Tombamento',
            ),
        ),
        migrations.RunPython(
            limpar_presencas_em_feriados_existentes,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

