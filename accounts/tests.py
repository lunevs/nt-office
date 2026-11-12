import os
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse

User = get_user_model()
PASSWORD = 'Original-Safe-Phrase!297'
TEMP = 'Temporary-Safe-Phrase!386'
NEW = 'Changed-Safe-Phrase!493'

@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password=PASSWORD, first_name='Иван')
        self.member = User.objects.create_user('member', password=PASSWORD, first_name='Анна', last_name='Иванова')

    def test_registration_activation_and_login(self):
        response = self.client.post(reverse('register'), {'username': 'NewMember', 'first_name': 'Пётр', 'last_name': 'Петров', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertRedirects(response, reverse('pending'))
        person = User.objects.get(username='newmember')
        self.assertFalse(person.is_active)
        self.assertTrue(person.check_password(PASSWORD))
        self.assertNotEqual(person.password, PASSWORD)
        self.client.post(reverse('login'), {'username': 'newmember', 'password': PASSWORD})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertRedirects(self.client.get(reverse('home')), reverse('login') + '?next=/')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('activate', args=[person.pk])).status_code, 405)
        self.assertRedirects(self.client.post(reverse('activate', args=[person.pk])), reverse('users'))
        self.client.logout()
        self.assertRedirects(self.client.post(reverse('login'), {'username': 'NewMember', 'password': PASSWORD}), reverse('home'))

    def test_permissions_and_post_only_logout(self):
        self.client.force_login(self.member)
        for name in ['users', 'reset_password']:
            url = reverse(name, args=[self.admin.pk]) if name == 'reset_password' else reverse(name)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('activate', args=[self.admin.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))

    def test_reset_invalidates_sessions_and_requires_change(self):
        member_client = Client()
        member_client.force_login(self.member)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse('reset_password', args=[self.member.pk]), {'new_password1': TEMP, 'new_password2': TEMP}), reverse('users'))
        self.assertEqual(member_client.get(reverse('profile')).status_code, 302)
        self.assertNotIn('_auth_user_id', member_client.session)
        self.assertFalse(member_client.login(username='member', password=PASSWORD))
        self.assertRedirects(member_client.post(reverse('login'), {'username': 'member', 'password': TEMP}), reverse('password_change'))
        self.assertRedirects(member_client.get(reverse('home')), reverse('password_change'))
        response = member_client.post(reverse('password_change'), {'old_password': TEMP, 'new_password1': NEW, 'new_password2': NEW})
        self.assertRedirects(response, reverse('profile'))
        self.member.refresh_from_db()
        self.assertFalse(self.member.must_change_password)
        self.assertTrue(self.member.check_password(NEW))
        self.assertEqual(member_client.get(reverse('home')).status_code, 200)

    def test_case_insensitive_unique_login(self):
        response = self.client.post(reverse('register'), {'username': 'MEMBER', 'first_name': 'Другой', 'last_name': 'Человек', 'password1': PASSWORD, 'password2': PASSWORD})
        self.assertContains(response, 'Этот логин уже занят.')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('MEMBER', password=PASSWORD)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('register'), {}).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('activate', args=[self.member.pk])).status_code, 403)
        self.assertEqual(client.post(reverse('reset_password', args=[self.member.pk]), {}).status_code, 403)

    def test_login_throttling(self):
        for _ in range(10):
            self.assertEqual(self.client.post(reverse('login'), {'username': 'member', 'password': 'wrong'}).status_code, 200)
        self.assertEqual(self.client.post(reverse('login'), {'username': 'member', 'password': PASSWORD}).status_code, 429)

    def test_weak_password_rejected(self):
        response = self.client.post(reverse('register'), {'username': 'weak', 'first_name': 'А', 'last_name': 'Б', 'password1': '123', 'password2': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='weak').exists())

    def test_health_and_pages(self):
        self.assertEqual(self.client.get(reverse('health')).json(), {'status': 'ok'})
        for name in ['login', 'register', 'pending']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.client.force_login(self.admin)
        for name in ['home', 'profile', 'users', 'password_change']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_bootstrap_never_overwrites_existing_account(self):
        env = {'BOOTSTRAP_ADMIN_LOGIN': 'member', 'BOOTSTRAP_ADMIN_PASSWORD': TEMP}
        with patch.dict(os.environ, env):
            call_command('bootstrap_admin', stdout=StringIO())
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser)
        self.assertTrue(self.member.check_password(PASSWORD))

    def test_bootstrap_creates_once_and_forces_password_change(self):
        self.admin.delete()
        with patch.dict(os.environ, {'BOOTSTRAP_ADMIN_LOGIN': 'owner', 'BOOTSTRAP_ADMIN_PASSWORD': TEMP}):
            call_command('bootstrap_admin', stdout=StringIO())
            call_command('bootstrap_admin', stdout=StringIO())
        owner = User.objects.get(username='owner')
        self.assertTrue(owner.is_administrator)
        self.assertTrue(owner.must_change_password)
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)

    def test_role_password_minimum_and_help(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from .forms import AccountPasswordChangeForm, TemporaryPasswordForm, RegistrationForm
        validate_password('Zq!8v', self.member)
        with self.assertRaises(ValidationError):
            validate_password('Zq!8', self.member)
        with self.assertRaises(ValidationError):
            validate_password('Zq!8v', self.admin)
        validate_password('Zq!8vTr#6L', self.admin)
        for person, minimum in [(self.member, 5), (self.admin, 10)]:
            for form_class in [AccountPasswordChangeForm, TemporaryPasswordForm]:
                self.assertIn(f'не менее {minimum} символов', form_class(person).fields['new_password1'].help_text)
        self.assertNotIn('похож', RegistrationForm().fields['password1'].help_text)
