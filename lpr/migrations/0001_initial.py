# Generated for the Selos Linux LPR integration.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("people", "0001_initial"),
        ("vehicles", "0002_alter_vehicle_proprietario"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatePassage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("captured_at", models.DateTimeField(db_index=True, verbose_name="data/hora")),
                ("plate", models.CharField(db_index=True, max_length=12, verbose_name="placa detectada")),
                ("camera_name", models.CharField(max_length=120, verbose_name="câmera")),
                ("camera_ip", models.GenericIPAddressField(verbose_name="IP da câmera")),
                ("lane", models.CharField(blank=True, max_length=20, verbose_name="faixa")),
                ("camera_direction", models.CharField(choices=[("forward", "Frente"), ("reverse", "Reverso"), ("unknown", "Desconhecida")], default="unknown", max_length=20, verbose_name="direção da câmera")),
                ("movement", models.CharField(choices=[("ENTRADA", "Entrada"), ("SAIDA", "Saída"), ("PASSAGEM", "Passagem")], db_index=True, default="PASSAGEM", max_length=20, verbose_name="movimento")),
                ("pic_name", models.CharField(max_length=80, verbose_name="identificador da imagem")),
                ("plate_image", models.ImageField(blank=True, upload_to="lpr/", verbose_name="imagem da placa")),
                ("raw_country", models.CharField(blank=True, max_length=20, verbose_name="país informado pela câmera")),
                ("matched_automatically", models.BooleanField(default=False, verbose_name="vínculo automático")),
                ("seal_serial_snapshot", models.CharField(blank=True, max_length=24, verbose_name="selo no momento")),
                ("seal_status_snapshot", models.CharField(blank=True, max_length=20, verbose_name="situação do selo no momento")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("person", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lpr_passages", to="people.person", verbose_name="proprietário")),
                ("vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lpr_passages", to="vehicles.vehicle", verbose_name="veículo")),
            ],
            options={
                "verbose_name": "movimentação de placa",
                "verbose_name_plural": "movimentações de placas",
                "ordering": ("-captured_at", "-pk"),
                "constraints": [models.UniqueConstraint(fields=("camera_ip", "pic_name"), name="lpr_unique_camera_picture")],
            },
        ),
    ]
