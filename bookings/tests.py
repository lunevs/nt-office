from datetime import date, time
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import Event, Room
from .layout import day_layout

User = get_user_model()

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BookingTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('author', first_name='Анна', last_name='Иванова')
        self.other = User.objects.create_user('other', first_name='Пётр')
        self.admin = User.objects.create_superuser('admin')
        self.pending = User.objects.create_user('pending', is_active=False)
        self.rooms = list(Room.objects.all())
        self.client.force_login(self.author)
        self.data = {'title': 'Домашняя группа', 'date': '2026-11-12', 'start_time': '18:00', 'end_time': '19:30', 'rooms': [self.rooms[0].pk, self.rooms[1].pk], 'people_count': 12, 'responsible': self.other.pk}

    def create_event(self):
        self.client.post(reverse('event_create'), self.data)
        return Event.objects.get()

    def test_create_multiple_rooms_and_day_navigation(self):
        event = self.create_event()
        self.assertEqual(event.author, self.author)
        self.assertEqual(event.responsible, self.other)
        self.assertEqual(event.rooms.count(), 2)
        response = self.client.get(reverse('home'), {'date': '2026-11-12'})
        self.assertContains(response, 'Домашняя группа')
        self.assertContains(response, 'Основной зал')
        self.assertContains(response, 'Класс 1')
        self.assertContains(response, '?date=2026-11-13')
        self.assertNotContains(self.client.get(reverse('home'), {'date': '2026-11-13'}), 'Домашняя группа')
        self.assertContains(self.client.get(reverse('event_detail', args=[event.pk])), 'Пётр')

    def test_author_and_admin_edit_but_responsible_cannot(self):
        event = self.create_event()
        url = reverse('event_edit', args=[event.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {**self.data, 'title': 'Запрещено'}).status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.title, self.data['title'])
        for person in (self.author, self.admin):
            self.client.force_login(person)
            self.assertEqual(self.client.post(url, {**self.data, 'title': 'Перенесено', 'date': '2026-11-13', 'rooms': [self.rooms[2].pk], 'author': self.other.pk}).status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.author, self.author)
        self.assertEqual(event.date, date(2026, 11, 13))
        self.assertEqual(list(event.rooms.all()), [self.rooms[2]])

    def test_invalid_times_and_required_fields(self):
        cases = [dict(start_time='05:59'), dict(end_time='23:01'), dict(start_time='22:00', end_time='07:00'), dict(end_time='18:00'), dict(people_count=0), dict(people_count=-1), dict(rooms=[]), dict(responsible=self.pending.pk), dict(title=' '), dict(date='nonsense'), dict(start_time='18:00:01')]
        for change in cases:
            with self.subTest(change=change):
                response = self.client.post(reverse('event_create'), {**self.data, **change})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(Event.objects.exists())

    def test_boundaries_and_overlaps_allowed(self):
        self.client.post(reverse('event_create'), {**self.data, 'start_time': '06:00', 'end_time': '23:00'})
        self.client.post(reverse('event_create'), self.data)
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(self.client.get(reverse('home'), {'date': self.data['date']}).status_code, 200)

    def test_authentication_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('home')).status_code, 302)
        self.assertEqual(self.client.post(reverse('event_create'), self.data).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author)
        self.assertEqual(client.post(reverse('event_create'), self.data).status_code, 403)
        self.assertFalse(Event.objects.exists())

    def test_invalid_date_navigation_and_selected_create_date(self):
        for value in ['bad', '0001-01-01', '9999-12-31']:
            self.assertEqual(self.client.get(reverse('home'), {'date': value}).status_code, 200)
        form = self.client.get(reverse('event_create'), {'date': '2026-12-25'}).context['form']
        self.assertEqual(form.initial['date'], date(2026, 12, 25))
        self.assertEqual(form.initial['responsible'], self.author)

    def test_dense_layout_and_adjacent_intervals(self):
        events = []
        for start, end in [(time(10), time(11)), (time(10, 15), time(10, 30)), (time(10, 20), time(10, 40)), (time(11), time(12))]:
            events.append(Event(start_time=start, end_time=end))
        layout = day_layout(events)
        self.assertEqual(len(layout['groups']), 2)
        self.assertTrue(layout['groups'][0]['stacked'])
        self.assertGreaterEqual(layout['groups'][0]['height'], 3 * 84)
        self.assertFalse(layout['groups'][1]['stacked'])
        self.assertEqual(layout['hours'][0]['label'], '10:00')
        self.assertEqual(layout['hours'][-1]['label'], '12:00')

    def test_empty_day_has_no_timeline(self):
        response = self.client.get(reverse('home'), {'date': '2026-11-12'})
        self.assertContains(response, 'Мероприятий не запланировано')
        self.assertNotContains(response, 'class="timeline"')

    def test_timeline_trims_to_exact_event_bounds(self):
        layout = day_layout([Event(start_time=time(18, 15), end_time=time(19, 45))])
        self.assertEqual(layout['hours'][0]['label'], '18:15')
        self.assertEqual(layout['hours'][-1]['label'], '19:45')
        self.assertEqual(layout['groups'][0]['top'], 0)
        self.assertEqual(layout['height'], layout['groups'][0]['height'])
        self.assertLess(layout['height'], 140)

    def test_profile_shows_three_nearest_responsible_meetings(self):
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 11, 12, 12, tzinfo=ZoneInfo('Europe/Belgrade'))
        for day, start, end, title, responsible in [
            (12, '10:00', '11:00', 'Завершённая', self.author),
            (12, '11:00', '13:00', 'Текущая', self.author),
            (12, '14:00', '15:00', 'Чужая', self.other),
            (12, '18:00', '19:00', 'Вечерняя', self.author),
            (13, '10:00', '11:00', 'Завтрашняя', self.author),
            (14, '10:00', '11:00', 'Четвёртая', self.author),
        ]:
            Event.objects.create(title=title, date=date(2026, 11, day), start_time=start, end_time=end, people_count=2, author=self.other, responsible=responsible)
        with patch('accounts.views.timezone.localtime', return_value=now):
            response = self.client.get(reverse('profile'))
        self.assertEqual([e['title'] for e in response.context['upcoming_events']], ['Текущая', 'Вечерняя', 'Завтрашняя'])
        self.assertContains(response, 'Мои ближайшие встречи')
        self.assertNotContains(response, 'Чужая')

    def test_profile_edit_changes_only_own_fields_and_login_stays_unique(self):
        self.assertRedirects(self.client.post(reverse('profile_edit', args=['name']), {'first_name': 'Новое', 'last_name': 'Имя', 'is_superuser': True}), reverse('profile'))
        self.author.refresh_from_db()
        self.assertEqual(self.author.first_name, 'Новое')
        self.assertFalse(self.author.is_superuser)
        response = self.client.post(reverse('profile_edit', args=['login']), {'username': 'OTHER'})
        self.assertContains(response, 'Этот логин уже занят.')
        self.assertRedirects(self.client.post(reverse('profile_edit', args=['login']), {'username': 'NewLogin'}), reverse('profile'))
        self.author.refresh_from_db()
        self.assertEqual(self.author.username, 'newlogin')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)
        self.other.refresh_from_db()
        self.assertEqual(self.other.username, 'other')

    def test_status_workflow_and_permissions(self):
        event = self.create_event()
        def action(name):
            return reverse('event_status', args=[event.pk, name])
        self.assertEqual(event.status, Event.Status.PENDING)
        self.assertEqual(self.client.get(action('cancel')).status_code, 405)
        self.assertEqual(self.client.post(action('confirm')).status_code, 403)
        self.client.force_login(self.other)
        for name in ['cancel', 'confirm', 'resubmit']:
            self.assertEqual(self.client.post(action(name)).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(action('confirm')).status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CONFIRMED)
        self.client.force_login(self.author)
        self.client.post(action('cancel'))
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELLED)
        self.assertNotContains(self.client.get(reverse('home'), {'date': self.data['date']}), self.data['title'])
        self.assertContains(self.client.get(reverse('events_cancelled')), self.data['title'])
        self.client.post(reverse('event_edit', args=[event.pk]), {**self.data, 'title': 'Исправленная'})
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELLED)
        self.client.post(action('resubmit'))
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PENDING)

    def test_author_schedule_changes_require_confirmation_again(self):
        event = self.create_event()
        url = reverse('event_edit', args=[event.pk])
        for change in [{'date': '2026-11-13'}, {'start_time': '18:15'}, {'end_time': '20:00'}, {'rooms': [self.rooms[2].pk]}]:
            event.status = Event.Status.CONFIRMED
            event.save()
            self.client.post(url, {**self.data, **change})
            event.refresh_from_db()
            self.assertEqual(event.status, Event.Status.PENDING)
        self.client.post(url, self.data)
        event.refresh_from_db()
        event.status = Event.Status.CONFIRMED
        event.save()
        self.client.post(url, {**self.data, 'title': 'Новое название'})
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CONFIRMED)
        self.client.force_login(self.admin)
        self.client.post(url, {**self.data, 'date': '2026-11-15'})
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CONFIRMED)

    def test_conflicts_require_shared_room_and_strict_overlap(self):
        event = self.create_event()
        def extra(start, end, room, status=Event.Status.PENDING):
            other = Event.objects.create(title='Другая', date=event.date, start_time=start, end_time=end, author=self.other, responsible=self.other, people_count=3, status=status)
            other.rooms.add(room)
            return other
        overlap = extra('19:00', '20:00', self.rooms[0])
        extra('19:30', '20:30', self.rooms[0])
        extra('17:00', '18:00', self.rooms[0])
        extra('18:00', '19:00', self.rooms[2])
        extra('18:00', '19:00', self.rooms[0], Event.Status.CANCELLED)
        self.assertEqual(list(event.conflicts()), [overlap])
        response = self.client.get(reverse('home'), {'date': self.data['date']})
        self.assertContains(response, '⚠ Пересечение')
        self.client.force_login(self.admin)
        self.client.post(reverse('event_status', args=[event.pk, 'confirm']))
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CONFIRMED)
        event.status = Event.Status.CANCELLED
        event.save()
        self.assertFalse(event.conflicts().exists())
        self.assertFalse(overlap.conflicts().filter(pk=event.pk).exists())

    def test_hidden_details_protected_in_all_views_and_api(self):
        event = self.create_event()
        event.hide_details = True
        event.title = 'Секретная встреча 987'
        event.people_count = 7821
        event.save()
        # The assigned responsible person does not acquire the author's access.
        self.client.force_login(self.other)
        for url in [reverse('event_detail', args=[event.pk]), reverse('home') + '?date=' + self.data['date'], reverse('profile')]:
            response = self.client.get(url)
            self.assertNotContains(response, event.title)
            self.assertNotContains(response, '7821')
        data = self.client.get(reverse('event_data', args=[event.pk])).json()
        self.assertEqual(data['title'], 'Занято')
        self.assertNotIn('people_count', data)
        self.assertNotIn('author', data)
        self.assertEqual(data['responsible']['id'], self.other.pk)
        self.assertEqual(self.client.get(reverse('event_edit', args=[event.pk])).status_code, 403)
        event.status = Event.Status.CANCELLED
        event.save()
        self.assertNotContains(self.client.get(reverse('events_cancelled')), event.title)
        for person in [self.author, self.admin]:
            self.client.force_login(person)
            self.assertContains(self.client.get(reverse('event_detail', args=[event.pk])), event.title)
            self.assertEqual(self.client.get(reverse('event_data', args=[event.pk])).json()['people_count'], 7821)

    def test_management_pending_queue_and_cancelled_profile_exclusion(self):
        event = self.create_event()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('users')), self.data['title'])
        self.client.post(reverse('event_status', args=[event.pk, 'confirm']))
        self.assertNotContains(self.client.get(reverse('users')), self.data['title'])
        self.client.post(reverse('event_status', args=[event.pk, 'cancel']))
        self.client.force_login(self.other)
        self.assertEqual(list(self.client.get(reverse('profile')).context['upcoming_events']), [])

    def test_status_actions_require_csrf_and_ignore_posted_status_on_create(self):
        self.client.post(reverse('event_create'), {**self.data, 'status': 'confirmed', 'hide_details': 'on'})
        event = Event.objects.get()
        self.assertEqual(event.status, Event.Status.PENDING)
        self.assertTrue(event.hide_details)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        for name in ['confirm', 'cancel', 'resubmit']:
            self.assertEqual(client.post(reverse('event_status', args=[event.pk, name])).status_code, 403)

    def test_cancelled_sorted_by_cancellation_time_not_event_date(self):
        from unittest.mock import patch
        from datetime import datetime
        from zoneinfo import ZoneInfo
        first = self.create_event()
        second = Event.objects.create(title='Более ранняя встреча', date=date(2026, 11, 1), start_time='10:00', end_time='11:00', author=self.author, responsible=self.author, people_count=1)
        for event, day in [(first, 15), (second, 16)]:
            with patch('bookings.views.timezone.now', return_value=datetime(2026, 11, day, 12, tzinfo=ZoneInfo('Europe/Belgrade'))):
                self.client.post(reverse('event_status', args=[event.pk, 'cancel']))
        first.refresh_from_db()
        stamp = first.cancelled_at
        self.client.post(reverse('event_status', args=[first.pk, 'cancel']))
        first.refresh_from_db()
        self.assertEqual(first.cancelled_at, stamp)
        response = self.client.get(reverse('events_cancelled'))
        self.assertEqual([event['pk'] for event in response.context['events']], [second.pk, first.pk])
        self.client.post(reverse('event_edit', args=[first.pk]), {**self.data, 'title': 'Исправление'})
        first.refresh_from_db()
        self.assertEqual(first.cancelled_at, stamp)
        self.client.post(reverse('event_status', args=[first.pk, 'resubmit']))
        first.refresh_from_db()
        self.assertIsNone(first.cancelled_at)

    def test_cancelled_list_scoped_to_author_for_members(self):
        own = self.create_event()
        own.status = Event.Status.CANCELLED
        own.save()
        other = Event.objects.create(title='Чужая отмена', date=own.date, start_time='10:00', end_time='11:00', author=self.other, responsible=self.author, people_count=2, status=Event.Status.CANCELLED)
        response = self.client.get(reverse('events_cancelled'))
        self.assertEqual([e['pk'] for e in response.context['events']], [own.pk])
        self.assertNotContains(response, other.title)
        self.assertContains(self.client.get(reverse('profile')), 'Мои отменённые мероприятия')
        self.client.force_login(self.admin)
        self.assertEqual(len(self.client.get(reverse('events_cancelled')).context['events']), 2)
        self.assertEqual(self.client.get(reverse('events_cancelled'), {'mine': '1'}).context['events'], [])

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SeriesTests(TestCase):
    setUp = BookingTests.setUp

    def series(self, **changes):
        data = {**self.data, 'repeat_weekly': 'on', 'repeat_until': '2026-12-03', **changes}
        response = self.client.post(reverse('event_create'), data)
        self.assertEqual(response.status_code, 302)
        return list(Event.objects.order_by('sequence'))

    def edit(self, event, **changes):
        data = {**self.data, 'date': event.date.isoformat(), 'scope': 'one', **changes}
        return self.client.post(reverse('event_edit', args=[event.pk]), data)

    def test_create_weekly_until_inclusive_and_nearest_day_redirect(self):
        from unittest.mock import patch
        with patch('bookings.views.timezone.localdate', return_value=date(2026, 11, 20)):
            response = self.client.post(reverse('event_create'), {**self.data, 'repeat_weekly': 'on', 'repeat_until': '2026-12-03'})
        self.assertEqual(response.url, '/?date=2026-11-26')
        events = list(Event.objects.order_by('sequence'))
        self.assertEqual([e.date for e in events], [date(2026, 11, 12), date(2026, 11, 19), date(2026, 11, 26), date(2026, 12, 3)])
        self.assertEqual(len({e.series_id for e in events}), 1)
        self.assertIsNotNone(events[0].series_id)
        self.assertTrue(all(e.rooms.count() == 2 and e.status == Event.Status.PENDING for e in events))

    def test_repeat_validation_and_single_occurrence_series(self):
        for until in ['', '2026-11-11', '2040-01-01']:
            response = self.client.post(reverse('event_create'), {**self.data, 'repeat_weekly': 'on', 'repeat_until': until})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Event.objects.exists())
        self.assertEqual(len(self.series(repeat_until='2026-11-12')), 1)

    def test_one_move_preserves_others_and_sequence(self):
        events = self.series()
        self.assertEqual(self.edit(events[1], date='2026-11-21').status_code, 302)
        moved = Event.objects.get(pk=events[1].pk)
        self.assertEqual(moved.date, date(2026, 11, 21))
        self.assertEqual(moved.sequence, 1)
        self.assertEqual(Event.objects.get(pk=events[2].pk).date, date(2026, 11, 26))
        # Even when moved before an earlier occurrence, future refers to series order.
        self.edit(moved, date='2026-11-10')
        self.client.post(reverse('event_status', args=[moved.pk, 'cancel']), {'scope': 'future'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CANCELLED).count(), 3)
        self.assertEqual(Event.objects.get(pk=events[0].pk).status, Event.Status.PENDING)

    def test_future_edit_preserves_previous_and_cancelled_status(self):
        events = self.series()
        Event.objects.update(status=Event.Status.CONFIRMED)
        Event.objects.filter(pk=events[3].pk).update(status=Event.Status.CANCELLED)
        response = self.edit(events[1], date='2026-11-20', start_time='17:00', scope='future', rooms=[self.rooms[2].pk])
        self.assertEqual(response.status_code, 302)
        items = list(Event.objects.order_by('sequence'))
        self.assertEqual(items[0].date, date(2026, 11, 12))
        self.assertEqual(items[0].status, Event.Status.CONFIRMED)
        self.assertEqual([e.date for e in items[1:]], [date(2026, 11, 20), date(2026, 11, 27), date(2026, 12, 4)])
        self.assertEqual([e.status for e in items[1:]], [Event.Status.PENDING, Event.Status.PENDING, Event.Status.CANCELLED])
        self.assertTrue(all(list(e.rooms.all()) == [self.rooms[2]] for e in items[1:]))

    def test_admin_future_edit_does_not_reset_confirmation(self):
        events = self.series()
        Event.objects.update(status=Event.Status.CONFIRMED)
        self.client.force_login(self.admin)
        self.edit(events[1], start_time='17:00', scope='future')
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 4)

    def test_cancel_one_or_future_and_resubmit(self):
        events = self.series()
        self.client.post(reverse('event_status', args=[events[1].pk, 'cancel']), {'scope': 'one'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CANCELLED).count(), 1)
        self.client.post(reverse('event_status', args=[events[2].pk, 'cancel']), {'scope': 'future'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CANCELLED).count(), 3)
        self.assertTrue(all(e.cancelled_at for e in Event.objects.filter(status=Event.Status.CANCELLED)))
        self.client.post(reverse('event_status', args=[events[1].pk, 'resubmit']), {'scope': 'future'})
        self.assertEqual(Event.objects.filter(status=Event.Status.PENDING).count(), 4)
        self.assertFalse(Event.objects.exclude(cancelled_at=None).exists())

    def test_other_user_cannot_mutate_series_and_status_per_occurrence(self):
        events = self.series()
        self.client.force_login(self.other)
        self.assertEqual(self.edit(events[0], scope='future').status_code, 403)
        self.assertEqual(self.client.post(reverse('event_status', args=[events[0].pk, 'cancel']), {'scope': 'future'}).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(reverse('event_status', args=[events[0].pk, 'confirm']), {'scope': 'future'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 4)

    def test_local_time_preserved_across_dst_and_conflicts_per_occurrence(self):
        events = self.series(date='2027-03-21', repeat_until='2027-04-04')
        self.assertEqual([e.start_time for e in events], [time(18)] * 3)
        self.assertEqual([e.date for e in events], [date(2027, 3, 21), date(2027, 3, 28), date(2027, 4, 4)])
        extra = Event.objects.create(title='Конфликт', date=events[1].date, start_time='18:30', end_time='19:00', people_count=3, author=self.other, responsible=self.other)
        extra.rooms.add(self.rooms[0])
        self.assertFalse(events[0].conflicts().exists())
        self.assertEqual(list(events[1].conflicts()), [extra])
        self.assertFalse(events[2].conflicts().exists())

    def test_series_form_and_detail_render(self):
        events = self.series()
        self.assertContains(self.client.get(reverse('event_edit', args=[events[0].pk])), 'Эта и все последующие встречи')
        self.assertContains(self.client.get(reverse('event_detail', args=[events[0].pk])), 'Еженедельная встреча')

    def test_bulk_confirmation_skips_cancelled_and_previous(self):
        events = self.series()
        Event.objects.filter(pk=events[2].pk).update(status=Event.Status.CANCELLED)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('event_status', args=[events[1].pk, 'confirm']), {'scope': 'future'})
        self.assertRedirects(response, reverse('users'))
        self.assertEqual(list(Event.objects.order_by('sequence').values_list('status', flat=True)), [Event.Status.PENDING, Event.Status.CONFIRMED, Event.Status.CANCELLED, Event.Status.CONFIRMED])

    def test_single_confirmation_is_default_and_series_grouped(self):
        events = self.series()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users'))
        cards = response.context['pending_events']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['count'], 4)
        self.assertEqual(cards[0]['pk'], events[0].pk)
        self.assertContains(response, 'На подтверждении: 4')
        self.client.post(reverse('event_status', args=[events[0].pk, 'confirm']))
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 1)
        response = self.client.get(reverse('users'))
        self.assertEqual(response.context['pending_events'][0]['pk'], events[1].pk)
        self.assertEqual(response.context['pending_events'][0]['count'], 3)

    def test_group_representative_preserves_series_order_after_move(self):
        events = self.series()
        self.edit(events[2], date='2026-11-01')
        self.client.force_login(self.admin)
        card = self.client.get(reverse('users')).context['pending_events'][0]
        self.assertEqual(card['pk'], events[0].pk)
        self.assertEqual(card['first_date'], date(2026, 11, 1))
        self.client.post(reverse('event_status', args=[card['pk'], 'confirm']), {'scope': 'future'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 4)

    def test_whole_series_confirmation_and_rejection_from_middle(self):
        events = self.series()
        Event.objects.filter(pk=events[2].pk).update(status=Event.Status.CANCELLED)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('event_detail', args=[events[1].pk]))
        self.assertContains(response, 'name="scope" value="all"', count=2)
        self.assertNotContains(response, 'Только эта встреча')
        self.client.post(reverse('event_status', args=[events[1].pk, 'confirm']), {'scope': 'all'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 3)
        self.assertEqual(Event.objects.get(pk=events[2].pk).status, Event.Status.CANCELLED)
        self.client.post(reverse('event_status', args=[events[1].pk, 'cancel']), {'scope': 'all'})
        self.assertEqual(Event.objects.filter(status=Event.Status.CANCELLED).count(), 4)

    def test_administrator_creates_confirmed_single_and_series(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('event_create'), self.data)
        self.assertEqual(Event.objects.get().status, Event.Status.CONFIRMED)
        self.client.post(reverse('event_create'), {**self.data, 'repeat_weekly': 'on', 'repeat_until': '2026-12-03'})
        self.assertEqual(Event.objects.count(), 5)
        self.assertEqual(Event.objects.filter(status=Event.Status.CONFIRMED).count(), 5)
        self.assertEqual(self.client.get(reverse('users')).context['pending_events'], [])
        self.client.force_login(self.author)
        self.client.post(reverse('event_create'), {**self.data, 'status': 'confirmed'})
        self.assertEqual(Event.objects.filter(status=Event.Status.PENDING).count(), 1)
