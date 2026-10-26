from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model('core', 'OperatingSettings').objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('core', '0002_operatingsettings')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
