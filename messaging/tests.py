from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import Message

User = get_user_model()

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MessagingTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', first_name='Анна', last_name='Иванова')
        self.bob = User.objects.create_user('bob', first_name='Борис', last_name='Петров')
        self.admin = User.objects.create_superuser('admin')
        self.pending = User.objects.create_user('pending', is_active=False)
        self.client.force_login(self.alice)

    def test_send_receive_reply_and_unread_badge(self):
        url = reverse('message_thread', args=[self.bob.pk])
        self.assertRedirects(self.client.post(url, {'text': 'Можно начать встречу позже?'}), url)
        message = Message.objects.get()
        self.assertEqual(message.sender, self.alice)
        self.assertEqual(message.recipient, self.bob)
        self.assertIsNone(message.read_at)
        self.client.force_login(self.bob)
        self.assertContains(self.client.get(reverse('messages')), 'Можно начать встречу позже?')
        self.assertEqual(self.client.get(reverse('profile')).context['unread_message_count'], 1)
        response = self.client.post(reverse('message_read', args=[self.alice.pk]), {'through': message.pk})
        self.assertEqual(response.json()['unread'], 0)
        self.assertRedirects(self.client.post(reverse('message_thread', args=[self.alice.pk]), {'text': 'Да, конечно.'}), reverse('message_thread', args=[self.alice.pk]))
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('messages')).context['conversations'][0]['unread'], 1)
        self.assertContains(self.client.get(url), 'Да, конечно.')

    def test_administrator_cannot_read_others_conversation(self):
        private = Message.objects.create(sender=self.alice, recipient=self.bob, text='Личное сообщение 54321')
        self.client.force_login(self.admin)
        for url in [reverse('messages'), reverse('message_thread', args=[self.alice.pk]), reverse('message_thread', args=[self.bob.pk])]:
            self.assertNotContains(self.client.get(url), private.text)
        response = self.client.get(reverse('message_updates', args=[self.bob.pk]))
        self.assertEqual(response.json()['messages'], [])
        self.client.post(reverse('message_read', args=[self.alice.pk]), {'through': private.pk})
        private.refresh_from_db()
        self.assertIsNone(private.read_at)

    def test_self_pending_and_unauthenticated_access(self):
        for person in [self.alice, self.pending]:
            self.assertEqual(self.client.get(reverse('message_thread', args=[person.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse('message_thread', args=[person.pk]), {'text': 'нет'}).status_code, 404)
        self.assertNotContains(self.client.get(reverse('message_people')), '@pending')
        self.client.logout()
        for url in [reverse('messages'), reverse('message_people'), reverse('message_thread', args=[self.bob.pk]), reverse('message_updates', args=[self.bob.pk])]:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('messages')).status_code, 302)
        self.assertFalse(Message.objects.exists())

    def test_send_validation_and_escaping(self):
        url = reverse('message_thread', args=[self.bob.pk])
        for value in [' ', '', 'x' * 5001]:
            response = self.client.post(url, {'text': value})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Message.objects.exists())
        text = '<script>alert("test")</script>\nВторая строка'
        self.client.post(url, {'text': text, 'sender': self.admin.pk, 'recipient': self.admin.pk})
        message = Message.objects.get()
        self.assertEqual(message.sender, self.alice)
        self.assertEqual(message.recipient, self.bob)
        self.assertContains(self.client.get(url), '&lt;script&gt;')
        self.assertNotContains(self.client.get(url), '<script>alert')
        self.assertEqual(self.client.get(reverse('message_updates', args=[self.bob.pk])).json()['messages'][0]['text'], text)

    def test_csrf_and_post_only_read(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(client.post(reverse('message_thread', args=[self.bob.pk]), {'text': 'Hello'}).status_code, 403)
        self.assertEqual(client.post(reverse('message_read', args=[self.bob.pk]), {'through': 1}).status_code, 403)
        self.assertEqual(self.client.get(reverse('message_read', args=[self.bob.pk])).status_code, 405)

    def test_history_and_incremental_updates(self):
        Message.objects.bulk_create([Message(sender=self.bob, recipient=self.alice, text=f'Сообщение {number}') for number in range(55)])
        items = list(Message.objects.order_by('pk'))
        response = self.client.get(reverse('message_thread', args=[self.bob.pk]))
        self.assertEqual([m.pk for m in response.context['items']], [m.pk for m in items[5:]])
        self.assertTrue(response.context['has_older'])
        earlier = self.client.get(reverse('message_thread', args=[self.bob.pk]), {'before': items[5].pk})
        self.assertEqual(len(earlier.context['items']), 5)
        updates = self.client.get(reverse('message_updates', args=[self.bob.pk]), {'after': items[52].pk}).json()['messages']
        self.assertEqual([m['id'] for m in updates], [m.pk for m in items[53:]])
        self.assertFalse(any(m['own'] for m in updates))
        for value in ['bad', '-1', '99999999999999999999999999999999999999999']:
            self.assertEqual(self.client.get(reverse('message_updates', args=[self.bob.pk]), {'after': value}).status_code, 200)

    def test_read_only_selected_sender_and_through_cursor(self):
        first = Message.objects.create(sender=self.bob, recipient=self.alice, text='Первое')
        second = Message.objects.create(sender=self.bob, recipient=self.alice, text='Второе')
        third = Message.objects.create(sender=self.admin, recipient=self.alice, text='Третье')
        self.client.post(reverse('message_read', args=[self.bob.pk]), {'through': first.pk})
        first.refresh_from_db(); second.refresh_from_db(); third.refresh_from_db()
        self.assertIsNotNone(first.read_at)
        self.assertIsNone(second.read_at)
        self.assertIsNone(third.read_at)

    def test_people_search_and_contact_from_event(self):
        from datetime import date
        from bookings.models import Event
        response = self.client.get(reverse('message_people'), {'q': 'Борис'})
        self.assertContains(response, '@bob')
        self.assertNotContains(response, '@alice')
        event = Event.objects.create(title='Встреча', date=date(2026, 11, 12), start_time='10:00', end_time='11:00', people_count=3, author=self.alice, responsible=self.bob)
        self.assertContains(self.client.get(reverse('event_detail', args=[event.pk])), reverse('message_thread', args=[self.bob.pk]))
