from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="ramal",
            field=models.CharField(blank=True, max_length=30, verbose_name="ramal"),
        ),
    ]
