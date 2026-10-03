from django.db import migrations, models


def classify(value):
    value = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    if len(value) == 7 and value[:3].isalpha() and value[3:].isdigit():
        return "ANTIGA"
    if (
        len(value) == 7
        and value[:3].isalpha()
        and value[3].isdigit()
        and value[4].isalpha()
        and value[5:].isdigit()
    ):
        return "MERCOSUL"
    return "DESCONHECIDA"


def fill_existing(apps, schema_editor):
    PlatePassage = apps.get_model("lpr", "PlatePassage")
    for passage in PlatePassage.objects.all().iterator():
        plate = "".join(ch for ch in (passage.plate or "").upper() if ch.isalnum())
        passage.raw_plate = plate
        passage.plate_format = classify(plate)
        passage.match_method = "EXATA" if passage.vehicle_id else "NAO_ENCONTRADA"
        passage.match_note = (
            "Registro anterior à correção Mercosul; leitura preservada como recebida."
        )
        passage.save(update_fields=("raw_plate", "plate_format", "match_method", "match_note"))


class Migration(migrations.Migration):
    dependencies = [
        ("lpr", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="platepassage",
            name="raw_plate",
            field=models.CharField(blank=True, db_index=True, max_length=12, verbose_name="placa lida pela câmera"),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="plate_format",
            field=models.CharField(
                choices=[("ANTIGA", "Padrão antigo"), ("MERCOSUL", "Mercosul"), ("DESCONHECIDA", "Desconhecido")],
                db_index=True,
                default="DESCONHECIDA",
                max_length=20,
                verbose_name="padrão da placa",
            ),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="match_method",
            field=models.CharField(
                choices=[("EXATA", "Leitura exata"), ("OCR", "Correção OCR"), ("NAO_ENCONTRADA", "Não cadastrada"), ("REVISAO", "Revisão necessária")],
                db_index=True,
                default="NAO_ENCONTRADA",
                max_length=24,
                verbose_name="método de vínculo",
            ),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="match_note",
            field=models.CharField(blank=True, max_length=255, verbose_name="detalhe da leitura"),
        ),
        migrations.AlterField(
            model_name="platepassage",
            name="plate",
            field=models.CharField(db_index=True, max_length=12, verbose_name="placa identificada"),
        ),
        migrations.RunPython(fill_existing, migrations.RunPython.noop),
    ]
