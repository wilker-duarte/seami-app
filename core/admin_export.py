import csv
import json
from datetime import date, datetime
from django.http import HttpResponse
from django.utils import timezone


def get_field_value_for_export(obj, field):
    """
    Retorna o valor formatado de um campo de modelo para exportação.
    Trata campos com choices, ForeignKeys, datas, booleans e nulos.
    """
    try:
        # Se o campo tiver choices, pega o label legível
        if hasattr(field, 'choices') and field.choices:
            display_method = f"get_{field.name}_display"
            if hasattr(obj, display_method):
                val = getattr(obj, display_method)()
                return val if val is not None else ""

        val = getattr(obj, field.name, None)

        if val is None:
            return ""
        
        if isinstance(val, bool):
            return "Sim" if val else "Não"
        
        if isinstance(val, (datetime,)):
            return timezone.localtime(val).strftime("%d/%m/%Y %H:%M:%S") if timezone.is_aware(val) else val.strftime("%d/%m/%Y %H:%M:%S")
        
        if isinstance(val, (date,)):
            return val.strftime("%d/%m/%Y")
        
        if hasattr(val, 'all'):  # ManyToManyField
            return ", ".join(str(item) for item in val.all())
        
        return str(val)
    except Exception:
        return ""


def export_as_csv_action(modeladmin, request, queryset):
    """
    Ação do Django Admin para exportar registros selecionados em formato CSV (compatível com Excel).
    Utiliza delimitador ';' e codificação 'utf-8-sig'.
    """
    opts = modeladmin.model._meta
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"export_{opts.app_label}_{opts.model_name}_{timestamp}.csv"

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=";")

    # Identifica os campos do modelo (excluindo senhas ou campos binários sensíveis se houver)
    fields = [
        f for f in opts.get_fields()
        if not f.is_relation or f.one_to_one or (f.many_to_one and hasattr(f, 'name'))
    ]
    # Remove senhas e hashes
    fields = [f for f in fields if f.name not in ['password']]

    # Cabeçalho formatado com verbose_name
    header = [
        getattr(f, 'verbose_name', f.name).title() if hasattr(f, 'verbose_name') else f.name.title()
        for f in fields
    ]
    writer.writerow(header)

    # Linhas de dados
    for obj in queryset.iterator():
        row = [get_field_value_for_export(obj, f) for f in fields]
        writer.writerow(row)

    return response


export_as_csv_action.short_description = "📥 Exportar selecionados para CSV (Excel)"


def export_as_json_action(modeladmin, request, queryset):
    """
    Ação do Django Admin para exportar registros selecionados em formato JSON estruturado.
    """
    opts = modeladmin.model._meta
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"export_{opts.app_label}_{opts.model_name}_{timestamp}.json"

    fields = [
        f for f in opts.get_fields()
        if not f.is_relation or f.one_to_one or (f.many_to_one and hasattr(f, 'name'))
    ]
    fields = [f for f in fields if f.name not in ['password']]

    data = []
    for obj in queryset.iterator():
        item = {}
        for f in fields:
            label = str(getattr(f, 'verbose_name', f.name))
            val = get_field_value_for_export(obj, f)
            item[label] = val
        data.append(item)

    response = HttpResponse(
        json.dumps(data, indent=2, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


export_as_json_action.short_description = "📥 Exportar selecionados para JSON"


class ExportActionMixin:
    """
    Mixin para adicionar ações de exportação em ModelAdmins.
    """
    actions = [export_as_csv_action, export_as_json_action]
