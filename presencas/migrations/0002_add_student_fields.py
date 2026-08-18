from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='aluno',
            name='acompanhamento_obs',
            field=models.TextField(blank=True, verbose_name='Observações de Acompanhamento'),
        ),
        migrations.AddField(
            model_name='aluno',
            name='data_desligamento',
            field=models.DateField(blank=True, null=True, verbose_name='Data de Desligamento'),
        ),
        migrations.AddField(
            model_name='aluno',
            name='data_entrada',
            field=models.DateField(blank=True, null=True, verbose_name='Data de Entrada'),
        ),
        migrations.AddField(
            model_name='aluno',
            name='has_acompanhamento',
            field=models.BooleanField(default=False, verbose_name='Possui Acompanhamento Especial'),
        ),
        migrations.AddField(
            model_name='aluno',
            name='motivo_desligamento',
            field=models.TextField(blank=True, verbose_name='Motivo do Desligamento'),
        ),
        migrations.AddField(
            model_name='aluno',
            name='turno',
            field=models.CharField(choices=[('integral', 'Integral'), ('matutino', 'Matutino'), ('vespertino', 'Vespertino')], default='integral', max_length=20, verbose_name='Turno'),
        ),
        migrations.AlterField(
            model_name='aluno',
            name='nome',
            field=models.CharField(max_length=150, verbose_name='Nome da Criança'),
        ),
        migrations.AlterField(
            model_name='registropresenca',
            name='status',
            field=models.CharField(choices=[('PRESENTE', 'Presente (P)'), ('AUSENTE', 'Falta (F)'), ('JUSTIFICADO', 'Falta Justificada (FJ)'), ('RECESSO', 'Recesso Escolar (RE)'), ('FERIADO', 'Feriado (FE)')], default='PRESENTE', max_length=20, verbose_name='Status'),
        ),
        migrations.AlterField(
            model_name='turma',
            name='nome',
            field=models.CharField(max_length=100, unique=True, verbose_name='Nome da Turma / Sala'),
        ),
    ]
