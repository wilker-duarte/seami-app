from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Turma',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, verbose_name='Nome da Turma')),
                ('faixa_etaria', models.CharField(blank=True, max_length=50, verbose_name='Faixa Etária')),
                ('ano_letivo', models.IntegerField(default=2026, verbose_name='Ano Letivo')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('professores', models.ManyToManyField(blank=True, related_name='turmas', to=settings.AUTH_USER_MODEL, verbose_name='Professores Responsáveis')),
            ],
            options={
                'verbose_name': 'Turma',
                'verbose_name_plural': 'Turmas',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='Aluno',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150, verbose_name='Nome Completo')),
                ('data_nascimento', models.DateField(blank=True, null=True, verbose_name='Data de Nascimento')),
                ('nome_responsavel', models.CharField(blank=True, max_length=150, verbose_name='Nome do Responsável')),
                ('telefone_responsavel', models.CharField(blank=True, max_length=20, verbose_name='Telefone do Responsável')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('turma', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alunos', to='presencas.turma', verbose_name='Turma')),
            ],
            options={
                'verbose_name': 'Aluno',
                'verbose_name_plural': 'Alunos',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='RegistroPresenca',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField(default=django.utils.timezone.now, verbose_name='Data')),
                ('status', models.CharField(choices=[('PRESENTE', 'Presente'), ('AUSENTE', 'Ausente'), ('JUSTIFICADO', 'Ausência Justificada')], default='PRESENTE', max_length=20, verbose_name='Status')),
                ('observacao', models.TextField(blank=True, verbose_name='Observação')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('aluno', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='presencas', to='presencas.aluno', verbose_name='Aluno')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Registrado por')),
                ('turma', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='registros_presenca', to='presencas.turma', verbose_name='Turma')),
            ],
            options={
                'verbose_name': 'Registro de Presença',
                'verbose_name_plural': 'Registros de Presença',
                'ordering': ['-data', 'aluno__nome'],
                'unique_together': {('aluno', 'data')},
            },
        ),
    ]
