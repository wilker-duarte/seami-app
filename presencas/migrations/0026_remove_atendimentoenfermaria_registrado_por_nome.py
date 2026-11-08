from django.db import migrations, models
from django.db.models import Q


def _nome_usuario(u):
    if not u:
        return ''
    full = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
    return full or (getattr(u, 'username', '') or '').strip()


def vincular_fk_usuario_enfermaria(apps, schema_editor):
    """
    Garante que todos os registros de AtendimentoEnfermaria (e ocorrências/presenças
    originadas na Enfermaria que ficaram sem FK de usuário) possuam vínculo FK real
    com um usuário (User) em registrado_por.
    """
    User = apps.get_model('accounts', 'User')
    AtendimentoEnfermaria = apps.get_model('presencas', 'AtendimentoEnfermaria')
    OcorrenciaCaderno = apps.get_model('presencas', 'OcorrenciaCaderno')
    RegistroPresenca = apps.get_model('presencas', 'RegistroPresenca')

    usuarios_ativos = list(User.objects.filter(is_active=True).order_by('id'))
    todos_usuarios = usuarios_ativos or list(User.objects.all().order_by('id'))
    if not todos_usuarios:
        return

    mapa_nomes = {}
    for u in todos_usuarios:
        nome_u = _nome_usuario(u).lower()
        if nome_u:
            mapa_nomes[nome_u] = u
        if u.username:
            mapa_nomes[u.username.lower()] = u

    default_user = (
        User.objects.filter(is_active=True, role__in=['ENFERMEIRA', 'DIRETOR', 'MASTER_ADMIN']).order_by('id').first()
        or User.objects.filter(is_active=True, is_superuser=True).order_by('id').first()
        or todos_usuarios[0]
    )
    default_nome = _nome_usuario(default_user)

    for at in AtendimentoEnfermaria.objects.filter(registrado_por__isnull=True):
        nome_antigo = (getattr(at, 'registrado_por_nome', '') or '').strip().lower()
        user_match = mapa_nomes.get(nome_antigo) or default_user
        AtendimentoEnfermaria.objects.filter(pk=at.pk).update(
            registrado_por=user_match,
            registrado_por_nome=''
        )

    ocorrs_sem_fk = OcorrenciaCaderno.objects.filter(
        registrado_por__isnull=True
    ).filter(
        Q(motivo__icontains='Enfermagem') |
        Q(motivo__icontains='Enfermaria') |
        Q(motivo__icontains='Afastamento Médico') |
        Q(observacao__icontains='Enfermagem') |
        Q(observacao__icontains='Enfermaria')
    )
    for oc in ocorrs_sem_fk:
        nome_antigo = (getattr(oc, 'registrado_por_nome', '') or '').strip().lower()
        user_match = mapa_nomes.get(nome_antigo) or default_user
        OcorrenciaCaderno.objects.filter(pk=oc.pk).update(
            registrado_por=user_match,
            registrado_por_nome=_nome_usuario(user_match) or default_nome
        )

    pres_sem_fk = RegistroPresenca.objects.filter(
        registrado_por__isnull=True
    ).filter(
        Q(observacao__icontains='Enfermagem') |
        Q(observacao__icontains='Enfermaria') |
        Q(observacao__icontains='Afastamento Médico')
    )
    for rp in pres_sem_fk:
        nome_antigo = (getattr(rp, 'registrado_por_nome', '') or '').strip().lower()
        user_match = mapa_nomes.get(nome_antigo) or default_user
        RegistroPresenca.objects.filter(pk=rp.pk).update(
            registrado_por=user_match,
            registrado_por_nome=_nome_usuario(user_match) or default_nome
        )


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0025_historicoalocacaoaluno'),
    ]

    operations = [
        migrations.RunPython(vincular_fk_usuario_enfermaria, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='atendimentoenfermaria',
            name='registrado_por_nome',
        ),
    ]
