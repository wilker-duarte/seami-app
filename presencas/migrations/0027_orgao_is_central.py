from django.db import migrations, models
from django.db.models import Q


def definir_ms_como_orgao_central(apps, schema_editor):
    """
    Define o MS (Ministério da Saúde) como o Órgão Central ao qual a creche pertence.
    """
    Orgao = apps.get_model('presencas', 'Orgao')
    ms_orgao = Orgao.objects.filter(
        Q(sigla__iexact='MS') |
        Q(nome__icontains='Ministério da Saúde') |
        Q(nome__icontains='Ministerio da Saude')
    ).first()

    if ms_orgao:
        Orgao.objects.exclude(pk=ms_orgao.pk).filter(is_central=True).update(is_central=False)
        ms_orgao.is_central = True
        if not ms_orgao.sigla:
            ms_orgao.sigla = 'MS'
        ms_orgao.save(update_fields=['is_central', 'sigla'])
    else:
        Orgao.objects.filter(is_central=True).update(is_central=False)
        Orgao.objects.create(
            nome='Ministério da Saúde',
            sigla='MS',
            descricao='Órgão Central (Mantenedor ao qual a creche pertence)',
            is_central=True,
            ativo=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0026_remove_atendimentoenfermaria_registrado_por_nome'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgao',
            name='is_central',
            field=models.BooleanField(default=False, verbose_name='Órgão Central (Mantenedor)'),
        ),
        migrations.AlterModelOptions(
            name='orgao',
            options={
                'ordering': ['-is_central', 'nome'],
                'verbose_name': 'Órgão (Central / Conveniado)',
                'verbose_name_plural': 'Órgãos (Central e Conveniados)',
            },
        ),
        migrations.RunPython(
            definir_ms_como_orgao_central,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

