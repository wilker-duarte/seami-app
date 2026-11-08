from django.db import migrations, models
from django.db.models import Q


def _nome_usuario(u):
    if not u:
        return ''
    full = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
    return full or (getattr(u, 'username', '') or '').strip()


def backfill_registrado_por_nome(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    DiarioDeClasse = apps.get_model('presencas', 'DiarioDeClasse')
    RegistroPresenca = apps.get_model('presencas', 'RegistroPresenca')
    OcorrenciaCaderno = apps.get_model('presencas', 'OcorrenciaCaderno')
    RegistroAmamentacao = apps.get_model('presencas', 'RegistroAmamentacao')
    DiaNaoLetivo = apps.get_model('presencas', 'DiaNaoLetivo')
    AtendimentoEnfermaria = apps.get_model('presencas', 'AtendimentoEnfermaria')

    enf_user = User.objects.filter(role='ENFERMEIRA').order_by('-is_active', 'id').first()
    enf_nome = _nome_usuario(enf_user) if enf_user else ''
    if not enf_nome:
        try:
            ConviteUsuario = apps.get_model('accounts', 'ConviteUsuario')
            conv = ConviteUsuario.objects.filter(role='ENFERMEIRA').order_by('-id').first()
            if conv and conv.nome:
                enf_nome = conv.nome.strip()
        except Exception:
            pass
    if not enf_nome:
        enf_nome = 'Enfermeira'

    # 1. Preenche registrado_por_nome para todos os registros que possuem registrado_por vinculado
    for model_cls in (
        DiarioDeClasse,
        RegistroPresenca,
        OcorrenciaCaderno,
        RegistroAmamentacao,
        DiaNaoLetivo,
        AtendimentoEnfermaria,
    ):
        for obj in model_cls.objects.filter(registrado_por__isnull=False).select_related('registrado_por'):
            nome = _nome_usuario(obj.registrado_por)
            if nome and obj.registrado_por_nome != nome:
                model_cls.objects.filter(pk=obj.pk).update(registrado_por_nome=nome)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_alter_conviteusuario_role_alter_user_role'),
        ('presencas', '0021_orgao_aluno_orgao_aluno_orgao_responsavel_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimentoenfermaria',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.AddField(
            model_name='dianaoletivo',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.AddField(
            model_name='diariodeclasse',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.AddField(
            model_name='ocorrenciacaderno',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.AddField(
            model_name='registroamamentacao',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.AddField(
            model_name='registropresenca',
            name='registrado_por_nome',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Registrado por (Nome)'),
        ),
        migrations.RunPython(backfill_registrado_por_nome, migrations.RunPython.noop),
    ]

