from django.db import migrations


def corrigir_faltas_justificadas(apps, schema_editor):
    RegistroPresenca = apps.get_model('presencas', 'RegistroPresenca')

    # Status constants
    STATUS_JUSTIFICADO = 'JUSTIFICADO'
    TURNO_JUSTIFICADO = 'JUSTIFICADO'
    TURNO_PRESENTE = 'PRESENTE'
    TURNO_AUSENTE = 'AUSENTE'

    registros = RegistroPresenca.objects.all()

    for reg in registros:
        obs = (reg.observacao or '').strip()
        obs_lower = obs.lower()
        precisa_salvar = False

        tem_evidencia_fj = (
            'falta justificada' in obs_lower or 
            'matutino fj' in obs_lower or 
            'vespertino fj' in obs_lower or
            '[fj' in obs_lower
        )

        if tem_evidencia_fj and reg.status != STATUS_JUSTIFICADO:
            reg.status = STATUS_JUSTIFICADO
            precisa_salvar = True

        if 'matutino fj' in obs_lower and getattr(reg, 'status_matutino', None) != TURNO_JUSTIFICADO:
            reg.status_matutino = TURNO_JUSTIFICADO
            precisa_salvar = True
        elif 'matutino ok' in obs_lower and getattr(reg, 'status_matutino', None) != TURNO_PRESENTE:
            reg.status_matutino = TURNO_PRESENTE
            precisa_salvar = True
        elif 'matutino falta' in obs_lower and getattr(reg, 'status_matutino', None) != TURNO_AUSENTE:
            reg.status_matutino = TURNO_AUSENTE
            precisa_salvar = True

        if 'vespertino fj' in obs_lower and getattr(reg, 'status_vespertino', None) != TURNO_JUSTIFICADO:
            reg.status_vespertino = TURNO_JUSTIFICADO
            precisa_salvar = True
        elif 'vespertino ok' in obs_lower and getattr(reg, 'status_vespertino', None) != TURNO_PRESENTE:
            reg.status_vespertino = TURNO_PRESENTE
            precisa_salvar = True
        elif 'vespertino falta' in obs_lower and getattr(reg, 'status_vespertino', None) != TURNO_AUSENTE:
            reg.status_vespertino = TURNO_AUSENTE
            precisa_salvar = True

        if precisa_salvar:
            reg.save()


def reverter_correcao(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0012_aluno_alergias_aluno_comorbidades_and_more'),
    ]

    operations = [
        migrations.RunPython(corrigir_faltas_justificadas, reverter_correcao),
    ]
