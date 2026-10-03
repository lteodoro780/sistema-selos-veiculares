from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lpr", "0002_ocr_mercosul"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="platepassage",
            name="match_method",
            field=models.CharField(
                choices=[
                    ("EXATA", "Leitura exata"),
                    ("OCR", "Correção OCR"),
                    ("MANUAL", "Correção manual"),
                    ("APRENDIDA", "Regra manual aprendida"),
                    ("NAO_ENCONTRADA", "Não cadastrada"),
                    ("REVISAO", "Revisão necessária"),
                ],
                db_index=True,
                default="NAO_ENCONTRADA",
                max_length=24,
                verbose_name="método de vínculo",
            ),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="manual_corrected_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="corrigida manualmente em"),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="manual_corrected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="lpr_manual_corrections",
                to=settings.AUTH_USER_MODEL,
                verbose_name="corrigida manualmente por",
            ),
        ),
        migrations.AddField(
            model_name="platepassage",
            name="manual_note",
            field=models.CharField(blank=True, max_length=255, verbose_name="observação da correção manual"),
        ),
        migrations.CreateModel(
            name="PlateCorrectionRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("raw_plate", models.CharField(db_index=True, max_length=12, verbose_name="leitura da câmera")),
                ("corrected_plate", models.CharField(db_index=True, max_length=12, verbose_name="placa correta")),
                ("camera_ip", models.CharField(blank=True, default="", help_text="Vazio aplica a qualquer câmera; normalmente a regra é criada para a câmera da passagem.", max_length=45, verbose_name="IP da câmera")),
                ("active", models.BooleanField(default=True, verbose_name="ativa")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lpr_correction_rules", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "regra manual de placa",
                "verbose_name_plural": "regras manuais de placas",
                "ordering": ("raw_plate", "camera_ip"),
            },
        ),
        migrations.AddConstraint(
            model_name="platecorrectionrule",
            constraint=models.UniqueConstraint(fields=("raw_plate", "camera_ip"), name="lpr_unique_manual_rule_by_camera"),
        ),
    ]
