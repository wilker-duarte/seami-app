from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('presencas', '0022_add_registrado_por_nome'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ocorrenciacaderno',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('falta', 'Falta'),
                    ('atestado', 'Atestado Médico'),
                    ('atraso', 'Atraso'),
                    ('saida', 'Saída Antecipada'),
                    ('amamentacao', 'Amamentação'),
                    ('extracao', 'Sala de Extração'),
                ],
                max_length=20,
                verbose_name='Tipo de Ocorrência',
            ),
        ),
        migrations.CreateModel(
            name='RegistroExtracao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField(unique=True, verbose_name='Data de Utilização')),
                ('quantidade', models.PositiveIntegerField(default=1, verbose_name='Quantidade de Utilizações da Sala no Dia')),
                ('ano', models.IntegerField(db_index=True, verbose_name='Ano')),
                ('mes', models.IntegerField(db_index=True, verbose_name='Mês')),
                ('observacao', models.TextField(blank=True, verbose_name='Observações')),
                ('anexo', models.FileField(blank=True, max_length=500, null=True, upload_to='attachments/extracao/', verbose_name='Arquivo Anexo')),
                ('attachment_name', models.CharField(blank=True, max_length=500, verbose_name='Nome do Arquivo Anexo')),
                ('attachment_type', models.CharField(blank=True, max_length=255, verbose_name='Tipo MIME do Anexo')),
                ('registrado_por_nome', models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                (
                    'modificado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='extracoes_modificadas',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Última modificação por',
                    ),
                ),
                (
                    'registrado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='extracoes_registradas',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Registrado por',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Registro da Sala de Extração',
                'verbose_name_plural': 'Registros da Sala de Extração (Espaço Materno)',
                'ordering': ['-data'],
                'indexes': [
                    models.Index(fields=['ano', 'mes'], name='presencas_r_ano_extr_idx'),
                    models.Index(fields=['data'], name='presencas_r_data_extr_idx'),
                ],
            },
        ),
    ]

