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

    def test_registration_gives_immediate_unverified_access(self):
        response = self.client.post(reverse('register'), {'username': 'NewMember', 'first_name': 'Пётр', 'last_name': 'Петров', 'password1': PASSWORD, 'password2': PASSWORD, 'is_superuser': 'on', 'verified': 'on'})
        self.assertRedirects(response, reverse('home'))
        person = User.objects.get(username='newmember')
        self.assertTrue(person.is_active)
        self.assertFalse(person.verified)
        self.assertFalse(person.is_superuser)
        self.assertTrue(person.check_password(PASSWORD))
        self.assertNotEqual(person.password, PASSWORD)
        self.assertEqual(self.client.session['_auth_user_id'], str(person.pk))
        self.assertContains(self.client.get(reverse('profile')), 'Аккаунт не подтверждён')
        self.client.logout()
        self.assertRedirects(self.client.post(reverse('login'), {'username': 'NewMember', 'password': PASSWORD}), reverse('home'))

    def test_verification_reject_and_only_admin_can_decide(self):
        from django.utils import timezone
        person = User.objects.create_user('waiting', password=PASSWORD, verification_requested_at=timezone.now())
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse('user_access', args=[person.pk, 'verify'])).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('users')), '@waiting')
        self.client.post(reverse('user_access', args=[person.pk, 'reject']))
        person.refresh_from_db()
        self.assertIsNone(person.verification_requested_at)
        self.assertFalse(person.verified)
        self.client.post(reverse('user_access', args=[person.pk, 'verify']))
        person.refresh_from_db()
        self.assertTrue(person.verified)

    def test_permissions_and_post_only_logout(self):
        self.client.force_login(self.member)
        for name in ['users', 'reset_password']:
            url = reverse(name, args=[self.admin.pk]) if name == 'reset_password' else reverse(name)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('user_access', args=[self.admin.pk,'block'])).status_code, 403)
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
        self.assertContains(response, 'Этот логин уже занят')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('MEMBER', password=PASSWORD)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('register'), {}).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('user_access', args=[self.member.pk,'block'])).status_code, 403)
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
        for name in ['login', 'register']:
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

    def test_block_revokes_sessions_even_after_unblock(self):
        active = Client()
        dormant = Client()
        active.force_login(self.member)
        dormant.force_login(self.member)
        self.client.force_login(self.admin)
        block = reverse('user_access', args=[self.member.pk, 'block'])
        unblock = reverse('user_access', args=[self.member.pk, 'unblock'])
        self.assertEqual(self.client.get(block).status_code, 405)
        self.assertRedirects(self.client.post(block), reverse('users'))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.session_version, 1)
        self.assertTrue(self.member.check_password(PASSWORD))
        self.assertEqual(active.get(reverse('home')).status_code, 302)
        self.assertFalse(active.login(username='member',password=PASSWORD))
        self.client.post(block)
        self.member.refresh_from_db()
        self.assertEqual(self.member.session_version, 1)
        self.assertRedirects(self.client.post(unblock), reverse('users'))
        self.assertEqual(active.get(reverse('home')).status_code, 302)
        self.assertNotIn('_auth_user_id', active.session)
        self.assertEqual(dormant.get(reverse('home')).status_code, 302)
        self.assertNotIn('_auth_user_id', dormant.session)
        self.assertTrue(dormant.login(username='member',password=PASSWORD))
        self.assertEqual(dormant.get(reverse('home')).status_code, 200)

    def test_block_permissions_and_self_protection(self):
        block = reverse('user_access',args=[self.admin.pk,'block'])
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(block).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(block).status_code,403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.client.get(reverse('home')).status_code,200)

    def test_management_lists_active_and_blocked_accounts(self):
        self.member.is_active=False
        self.member.save()
        self.client.force_login(self.admin)
        response=self.client.get(reverse('users'))
        self.assertContains(response,'Пользователи')
        self.assertContains(response,'@member')
        self.assertContains(response,'@admin')
        self.assertContains(response,'Заблокирован')
        self.assertContains(response,reverse('user_access',args=[self.member.pk,'unblock']))
        self.assertNotContains(response,reverse('user_access',args=[self.admin.pk,'block']))
        self.assertNotContains(response,'Ждут активации')

    def test_profile_save_cannot_undo_concurrent_block(self):
        from .forms import ProfileNameForm
        original_clean = ProfileNameForm.clean
        def block_during_validation(form):
            User.objects.filter(pk=form.instance.pk).update(is_active=False, session_version=1)
            return original_clean(form)
        self.client.force_login(self.member)
        with patch.object(ProfileNameForm, 'clean', block_during_validation):
            response = self.client.post(reverse('profile_edit',args=['name']), {'first_name':'Анна','last_name':'Новая'})
        self.assertEqual(response.status_code,302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.session_version,1)
        self.assertEqual(self.client.get(reverse('home')).status_code,302)


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AppShellTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password=PASSWORD, first_name='Иван')
        self.member = User.objects.create_user('member', password=PASSWORD, first_name='Анна', last_name='Иванова')

    def test_service_worker_is_served_from_root_without_login(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/javascript'))
        self.assertEqual(response['Cache-Control'], 'no-cache')
        body = response.content.decode()
        self.assertIn('"precache": ["/static/app.css"', body)
        self.assertIn('"^/events/\\\\d+/$"', body)
        self.assertNotIn('management', body)  # управление с временными паролями не сохраняется
        self.assertNotIn('{%', body)

    def test_service_worker_skips_forced_password_change(self):
        self.member.must_change_password = True
        self.member.save()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('service_worker')).status_code, 200)
        page = self.client.get(reverse('password_change'))
        self.assertNotContains(page, 'data-auth="in"')
        self.assertNotContains(page, 'data-toast="offline"')

    def test_offline_and_update_toasts_follow_mockups(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse('home'))
        self.assertContains(page, 'data-auth="in"')
        self.assertContains(page, 'Нет сети · показываем сохранённое расписание')
        self.assertContains(page, 'Доступна новая версия')
        self.assertContains(page, 'data-update-now>Обновить</button>')
        self.assertContains(page, 'pwa.js')
        self.client.logout()
        login = self.client.get(reverse('login'))
        self.assertContains(login, 'pwa.js')
        self.assertContains(login, 'data-sw="/sw.js"')
        self.assertNotContains(login, 'data-toast="offline"')

    def test_manifest_is_public_and_installable(self):
        response = self.client.get(reverse('manifest'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/manifest+json'))
        data = response.json()
        self.assertEqual(data['name'], 'Наш офис')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual({icon['sizes'] for icon in data['icons']}, {'192x192', '512x512'})
        self.assertIn('maskable', [icon.get('purpose') for icon in data['icons']])

    def test_manifest_not_redirected_during_forced_password_change(self):
        self.member.must_change_password = True
        self.member.save()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('manifest')).status_code, 200)
        response = self.client.get(reverse('password_change'))
        self.assertNotContains(response, 'class="tabbar"')
        self.assertNotContains(response, 'class="sidebar"')

    def test_pages_link_manifest_and_home_screen_icon(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'rel="manifest" href="/manifest.webmanifest"')
        self.assertContains(response, 'rel="apple-touch-icon"')
        self.assertNotContains(response, 'class="tabbar"')

    def test_management_gear_only_for_administrator(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'class="tabbar"')
        self.assertNotContains(response, 'aria-label="Управление"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('home')), 'aria-label="Управление"')


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MockupFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password=PASSWORD, first_name='Иван')
        self.member = User.objects.create_user('member', password=PASSWORD, first_name='Анна', last_name='Иванова')

    def test_blocked_message_only_with_correct_password(self):
        self.member.is_active = False
        self.member.save()
        wrong = self.client.post(reverse('login'), {'username': 'member', 'password': 'Wrong-Safe-Phrase!111'})
        self.assertContains(wrong, 'Неверный логин или пароль')
        self.assertNotContains(wrong, 'Аккаунт заблокирован')
        right = self.client.post(reverse('login'), {'username': 'member', 'password': PASSWORD})
        self.assertContains(right, 'Аккаунт заблокирован')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_registration_with_single_password_field_still_validates(self):
        response = self.client.post(reverse('register'), {'username': 'solo', 'first_name': 'Пётр', 'last_name': 'Петров', 'password1': PASSWORD})
        self.assertRedirects(response, reverse('home'))
        self.client.logout()
        self.assertTrue(User.objects.get(username='solo').check_password(PASSWORD))
        weak = self.client.post(reverse('register'), {'username': 'weak', 'first_name': 'Ян', 'last_name': 'Ли', 'password1': '12345678'})
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(User.objects.filter(username='weak').exists())

    def test_reset_password_shows_temporary_password_once(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse('reset_password', args=[self.member.pk]), {'new_password1': TEMP, 'new_password2': TEMP}), reverse('users'), fetch_redirect_response=False)
        first = self.client.get(reverse('users'))
        self.assertContains(first, 'Пароль сброшен')
        self.assertContains(first, TEMP)
        self.assertNotContains(self.client.get(reverse('users')), TEMP)

    def test_forced_password_change_does_not_ask_temporary_again(self):
        self.member.must_change_password = True
        self.member.save()
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse('password_change')), 'name="old_password"')
        self.assertRedirects(self.client.post(reverse('password_change'), {'new_password1': NEW, 'new_password2': NEW}), reverse('profile'))
        self.member.refresh_from_db()
        self.assertFalse(self.member.must_change_password)
        self.assertTrue(self.member.check_password(NEW))


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AdministratorRoleTests(TestCase):
    """Назначение и снятие прав администратора (макеты 38, 38б)."""

    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='Admin-Long-Phrase!2026', first_name='Иван')
        self.member = User.objects.create_user('member', password=PASSWORD, first_name='Ольга', last_name='Смирнова', verified=True)
        self.newbie = User.objects.create_user('newbie', password=PASSWORD, first_name='Пётр')
        self.client.force_login(self.admin)

    def test_management_shows_shield_and_admin_label(self):
        page = self.client.get(reverse('users'))
        self.assertContains(page, reverse('user_role', args=[self.member.pk]))
        self.assertNotContains(page, reverse('user_role', args=[self.newbie.pk]))  # сначала подтвердить
        self.assertNotContains(page, reverse('user_role', args=[self.admin.pk]))  # себе нельзя

    @patch('accounts.telegram.notify_role')
    def test_make_and_remove_administrator(self, notify):
        sheet = self.client.get(reverse('user_role', args=[self.member.pk]))
        self.assertContains(sheet, 'Сделать администратором?')
        self.assertContains(sheet, 'не короче 10 символов')
        self.assertRedirects(self.client.post(reverse('user_role', args=[self.member.pk])), reverse('users'))
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_administrator)
        self.assertTrue(self.member.must_change_password)  # пароль администратора — от 10 символов
        notify.assert_called_once()
        self.assertContains(self.client.get(reverse('users')), '@member · администратор')
        self.assertContains(self.client.get(reverse('user_role', args=[self.member.pk])), 'Снять права администратора?')
        self.client.post(reverse('user_role', args=[self.member.pk]))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser)
        self.assertTrue(self.member.is_verified)

    @patch('accounts.telegram.notify_role')
    def test_telegram_only_admin_keeps_signing_in_without_password_change(self, notify):
        self.member.set_unusable_password()
        self.member.save()
        self.assertNotContains(self.client.get(reverse('user_role', args=[self.member.pk])), 'не короче 10 символов')
        self.client.post(reverse('user_role', args=[self.member.pk]))
        self.member.refresh_from_db()
        self.assertEqual((self.member.is_superuser, self.member.must_change_password), (True, False))

    def test_guards(self):
        self.client.post(reverse('user_role', args=[self.newbie.pk]))
        self.newbie.refresh_from_db()
        self.assertFalse(self.newbie.is_superuser)
        self.assertEqual(self.client.post(reverse('user_role', args=[self.admin.pk])).status_code, 403)
        self.member.is_active = False
        self.member.save()
        self.assertEqual(self.client.post(reverse('user_role', args=[self.member.pk])).status_code, 403)
        self.client.force_login(self.newbie)
        self.assertEqual(self.client.post(reverse('user_role', args=[self.admin.pk])).status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)
