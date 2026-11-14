from django.db import migrations

RENAMES = [
    ('Класс 1', 'Бэнкси (класс с доской)'),
    ('Класс 2', 'Билибин (класс 2)'),
    ('Склад', 'Кубрик (склад)'),
]

def forwards(apps, schema_editor):
    Room = apps.get_model('bookings', 'Room')
    for old, new in RENAMES:
        Room.objects.filter(name=old).update(name=new)
    Room.objects.get_or_create(name='Кухня', defaults={'position': 4})

class Migration(migrations.Migration):
    dependencies = [('bookings', '0006_eventseries_event_sequence_event_series_and_more')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
