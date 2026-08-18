import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0004_diariodeclasse_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OcorrenciaCaderno',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('falta', 'Falta'), ('atestado', 'Atestado Médico'), ('atraso', 'Atraso'), ('saida', 'Saída Antecipada'), ('amamentacao', 'Amamentação')], max_length=20, verbose_name='Tipo de Ocorrência')),
                ('data', models.DateField(default=django.utils.timezone.now, verbose_name='Data do Evento')),
                ('data_fim', models.DateField(blank=True, null=True, verbose_name='Data de Término do Afastamento')),
                ('horario', models.TimeField(blank=True, null=True, verbose_name='Horário do Evento')),
                ('horario_retorno', models.TimeField(blank=True, null=True, verbose_name='Horário Previsto de Retorno')),
                ('retorna', models.BooleanField(default=False, verbose_name='Retorna no mesmo dia?')),
                ('justificado', models.BooleanField(default=False, verbose_name='Justificado?')),
                ('avisado_pais', models.BooleanField(default=False, verbose_name='Avisado previamente pelos pais?')),
                ('cid', models.CharField(blank=True, max_length=50, verbose_name='CID (Classificação Internacional de Doenças)')),
                ('motivo', models.TextField(blank=True, verbose_name='Motivo Declarado')),
                ('quantidade', models.CharField(blank=True, max_length=50, verbose_name='Quantidade / Sessão / Duração')),
                ('observacao', models.TextField(blank=True, verbose_name='Observações Adicionais')),
                ('documento', models.FileField(blank=True, null=True, upload_to='caderno_docs/%Y/%m/', verbose_name='Documento / Atestado Anexo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('aluno', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ocorrencias_caderno', to='presencas.aluno', verbose_name='Aluno / Criança')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Registrado por')),
                ('turma', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ocorrencias_caderno', to='presencas.turma', verbose_name='Sala / Turma')),
            ],
            options={
                'verbose_name': 'Ocorrência do Caderno SEAMI',
                'verbose_name_plural': 'Ocorrências do Caderno SEAMI',
                'ordering': ['-data', '-criado_em'],
            },
        ),
    ]
