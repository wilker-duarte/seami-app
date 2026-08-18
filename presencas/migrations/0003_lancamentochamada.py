from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('presencas', '0002_add_student_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='LancamentoChamada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField(default=django.utils.timezone.now, verbose_name='Data da Chamada')),
                ('turno', models.CharField(choices=[('all', 'Todos os Turnos'), ('integral', 'Integral'), ('matutino', 'Matutino'), ('vespertino', 'Vespertino')], default='all', max_length=20, verbose_name='Turno do Lançamento')),
                ('alunos_json', models.JSONField(default=list, verbose_name='Lista de Presenças (JSON)')),
                ('total_alunos', models.IntegerField(default=0, verbose_name='Total de Alunos')),
                ('total_presentes', models.IntegerField(default=0, verbose_name='Total Presentes')),
                ('total_faltas', models.IntegerField(default=0, verbose_name='Total Faltas')),
                ('total_justificadas', models.IntegerField(default=0, verbose_name='Total Justificadas')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Registrado por')),
                ('turma', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lancamentos_chamada', to='presencas.turma', verbose_name='Turma / Sala')),
            ],
            options={
                'verbose_name': 'Lançamento de Chamada',
                'verbose_name_plural': 'Lançamentos de Chamada',
                'ordering': ['-data', 'turma__nome'],
                'unique_together': {('turma', 'data', 'turno')},
            },
        ),
    ]
