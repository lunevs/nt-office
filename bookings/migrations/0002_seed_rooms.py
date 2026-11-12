from django.db import migrations

def seed(apps, schema_editor):
    Room = apps.get_model("bookings", "Room")
    for position, name in enumerate(["Основной зал", "Класс 1", "Класс 2", "Склад"]):
        Room.objects.get_or_create(name=name, defaults={"position": position})

class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
