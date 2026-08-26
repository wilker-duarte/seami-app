import os
import json
from django.db import migrations
from django.conf import settings


def popular_historico_frequencia(apps, schema_editor):
    HistoricoFrequenciaMensal = apps.get_model('presencas', 'HistoricoFrequenciaMensal')

    base_dir = getattr(settings, 'BASE_DIR', None)
    if base_dir:
        json_path = os.path.join(str(base_dir), 'data', 'historical_frequency.json')
    else:
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'historical_frequency.json')

    if not os.path.exists(json_path):
        # Fallback para busca no diretório do app ou projeto
        alt_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')), 'data', 'historical_frequency.json')
        if os.path.exists(alt_path):
            json_path = alt_path

    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                hist_data = json.load(f)

            for item in hist_data:
                m_str = item.get('month', '')
                if not m_str or '-' not in m_str:
                    continue
                parts = m_str.split('-')
                ano = int(parts[0])
                mes = int(parts[1])
                enrolled = int(item.get('enrolled', 0))
                present = int(item.get('present', 0))
                absent = max(0, enrolled - present)
                taxa = round((present / enrolled) * 100, 1) if enrolled > 0 else 0.0

                HistoricoFrequenciaMensal.objects.update_or_create(
                    mes_ano=m_str,
                    defaults={
                        'ano': ano,
                        'mes': mes,
                        'matriculados': enrolled,
                        'presentes_media': present,
                        'ausentes_media': absent,
                        'taxa_frequencia': taxa,
                        'observacao': f"Série histórica oficial consolidada ({m_str})"
                    }
                )
        except Exception as e:
            print(f"[Migration 0014] Erro ao popular histórico de frequência: {e}")


def reverter_populacao(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('presencas', '0013_corrigir_presencas_justificadas'),
    ]

    operations = [
        migrations.RunPython(popular_historico_frequencia, reverter_populacao),
    ]
