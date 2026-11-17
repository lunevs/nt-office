from datetime import date, time
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

class RemoveApprovalMigrationTests(TransactionTestCase):
    def test_existing_bookings_and_relations_survive(self):
        old = [('bookings', '0007_rename_rooms_add_kitchen'), ('accounts', '0002_user_session_version')]
        new = [('bookings', '0008_alter_event_status_event_event_valid_status'), ('accounts', '0002_user_session_version')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        User = apps.get_model('accounts', 'User')
        Event = apps.get_model('bookings', 'Event')
        Room = apps.get_model('bookings', 'Room')
        user = User.objects.create(username='migration-user')
        room = Room.objects.first()
        stamp = timezone.now()
        ids = []
        for status in ['pending', 'confirmed', 'cancelled']:
            event = Event.objects.create(title='Сохранить ' + status, date=date(2026,11,17), start_time=time(10), end_time=time(11), people_count=8, author_id=user.pk, responsible_id=user.pk, status=status, cancelled_at=stamp if status=='cancelled' else None)
            event.rooms.add(room)
            ids.append(event.pk)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        Event = apps.get_model('bookings', 'Event')
        self.assertEqual(list(Event.objects.filter(pk__in=ids).order_by('pk').values_list('status',flat=True)), ['active','active','cancelled'])
        self.assertEqual(Event.objects.get(pk=ids[2]).cancelled_at, stamp)
        for pk in ids:
            event = Event.objects.get(pk=pk)
            self.assertEqual(event.rooms.get().pk,room.pk)
            self.assertEqual(event.author_id,user.pk)
            self.assertEqual(event.people_count,8)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
