import hashlib
import hmac
import json
import time
from datetime import date, time as dtime
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import telegram

User = get_user_model()
TOKEN = "123456:TEST-token-for-signatures-only"
PASSWORD = "Original-Safe-Phrase!297"
STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


def webapp_init_data(user, auth_date=None, token=TOKEN):
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAH", "user": json.dumps(user, ensure_ascii=False, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def widget_params(user, auth_date=None):
    fields = {"id": str(user["id"]), "first_name": user.get("first_name", ""), "username": user.get("username", ""), "auth_date": str(auth_date or int(time.time()))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return fields


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, SITE_URL="https://office.example", TELEGRAM_WEBHOOK_SECRET="hook-secret", STORAGES=STATIC)
class TelegramAuthTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PASSWORD, first_name="Иван", telegram_id=900)
        self.member = User.objects.create_user("member", password=PASSWORD, first_name="Анна", last_name="Иванова")
        self.tg = {"id": 555, "first_name": "Никита", "last_name": "Никифоров", "username": "Nikita"}

    def auth(self, init_data):
        self.client.get(reverse("telegram_entry"))
        return self.client.post(reverse("telegram_auth"), {"init_data": init_data})

    def test_signature_checks(self):
        self.assertEqual(telegram.verify_webapp(webapp_init_data(self.tg))["id"], 555)
        self.assertIsNone(telegram.verify_webapp(webapp_init_data(self.tg, token="999:other")))
        self.assertIsNone(telegram.verify_webapp(webapp_init_data(self.tg, auth_date=int(time.time()) - 2 * 86400)))
        self.assertIsNone(telegram.verify_webapp(webapp_init_data(self.tg).replace("Nikita", "Hacker")))
        self.assertEqual(telegram.verify_login(widget_params(self.tg))["id"], 555)
        tampered = widget_params(self.tg)
        tampered["id"] = "556"
        self.assertIsNone(telegram.verify_login(tampered))

    def test_linked_user_signs_in_inside_telegram(self):
        self.member.telegram_id = 555
        self.member.save()
        response = self.auth(webapp_init_data(self.tg))
        self.assertEqual(response.json()["redirect"], reverse("home"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.member.pk))
        self.assertTrue(self.client.session["in_telegram"])
        self.assertContains(self.client.get(reverse("home")), "telegram-web-app.js")
        self.member.refresh_from_db()
        self.assertEqual(self.member.telegram_username, "Nikita")

    def test_bad_signature_is_rejected(self):
        response = self.auth(webapp_init_data(self.tg, token="999:other"))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.telegram.send")
    def test_unlinked_user_creates_account_from_telegram(self, send):
        self.assertEqual(self.auth(webapp_init_data(self.tg)).json()["redirect"], reverse("telegram_join"))
        page = self.client.get(reverse("telegram_join"))
        self.assertContains(page, "Здравствуйте, Никита!")
        self.assertContains(page, 'value="nikita"')
        response = self.client.post(reverse("telegram_join"), {"last_name": "Никифоров", "first_name": "Никита", "username": "nikita"})
        self.assertRedirects(response, reverse("home"))
        person = User.objects.get(username="nikita")
        self.assertEqual((person.telegram_id, person.is_active, person.verified, person.has_usable_password()), (555, True, False, False))
        self.assertEqual(self.client.session["_auth_user_id"], str(person.pk))
        send.assert_not_called()
        self.client.session.flush()
        self.assertEqual(self.auth(webapp_init_data(self.tg)).json()["redirect"], reverse("home"))

    def test_existing_account_links_telegram_with_password_once(self):
        self.auth(webapp_init_data(self.tg))
        response = self.client.post(reverse("telegram_link"), {"username": "member", "password": PASSWORD})
        self.assertRedirects(response, reverse("home"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.telegram_id, 555)
        self.client.session.flush()
        self.assertEqual(self.auth(webapp_init_data(self.tg)).json()["redirect"], reverse("home"))

    def test_blocked_user_is_not_signed_in(self):
        self.member.telegram_id = 555
        self.member.is_active = False
        self.member.save()
        self.assertEqual(self.auth(webapp_init_data(self.tg)).json()["redirect"], reverse("login") + "?blocked=1")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("login") + "?blocked=1"), "Аккаунт заблокирован")

    def test_site_widget_signs_in_or_links_current_account(self):
        self.member.telegram_id = 555
        self.member.save()
        self.assertRedirects(self.client.get(reverse("telegram_login"), widget_params(self.tg)), reverse("home"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.member.pk))
        self.client.force_login(self.admin)
        other = {"id": 777, "first_name": "Иван", "username": "ivan"}
        self.assertRedirects(self.client.get(reverse("telegram_login"), widget_params(other)), reverse("profile"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.telegram_id, 777)
        self.assertRedirects(self.client.get(reverse("telegram_login"), widget_params(self.tg)), reverse("profile"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.telegram_id, 777)  # чужой Telegram не перепривязывается

    def test_welcome_screen_offers_telegram_login(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, "Расписание офиса")
        self.assertContains(page, "https://oauth.telegram.org/auth?bot_id=123456")
        self.assertContains(self.client.get(reverse("login"), {"method": "password"}), 'name="password"')

    def test_frame_ancestors_allow_only_telegram_web(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response["Content-Security-Policy"], "frame-ancestors 'self' https://web.telegram.org")
        self.assertNotIn("X-Frame-Options", response)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, SITE_URL="https://office.example", TELEGRAM_WEBHOOK_SECRET="hook-secret", STORAGES=STATIC)
class TelegramBotTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PASSWORD, first_name="Иван", telegram_id=900)
        self.member = User.objects.create_user("member", password=PASSWORD, first_name="Анна", last_name="Иванова", telegram_id=901)
        from django.utils import timezone
        self.waiting = User.objects.create_user("waiting", password=PASSWORD, first_name="Пётр", verification_requested_at=timezone.now(), telegram_id=902)

    def hook(self, update, secret="hook-secret"):
        return self.client.post(reverse("telegram_webhook"), json.dumps(update), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

    @patch("accounts.telegram.call")
    def test_webhook_requires_secret_and_verifies_from_admin_button(self, call):
        self.assertEqual(self.hook({}, secret="wrong").status_code, 403)
        update = {"callback_query": {"id": "q1", "from": {"id": 901}, "data": f"verify:{self.waiting.pk}", "message": {"chat": {"id": 901}, "message_id": 5}}}
        self.hook(update)
        self.waiting.refresh_from_db()
        self.assertFalse(self.waiting.verified)  # не админ — не подтверждает
        update["callback_query"]["from"]["id"] = 900
        with patch("accounts.telegram.send") as send:
            self.hook(update)
        self.waiting.refresh_from_db()
        self.assertTrue(self.waiting.verified)
        self.assertIsNone(self.waiting.verification_requested_at)
        self.assertEqual(send.call_args[0][:2], (902, "Аккаунт подтверждён"))
        methods = [c.args[0] for c in call.call_args_list]
        self.assertIn("editMessageText", methods)
        self.assertIn("answerCallbackQuery", methods)

    @patch("accounts.telegram.call")
    def test_start_command_replies_with_app_button(self, call):
        self.hook({"message": {"text": "/start", "chat": {"id": 42}}})
        method, payload = call.call_args[0]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"], "https://office.example/tg/")

    @patch("accounts.telegram.send")
    def test_message_and_event_notifications_respect_settings(self, send):
        from bookings.models import Event, Room
        self.client.force_login(self.admin)
        self.client.post(reverse("message_thread", args=[self.member.pk]), {"text": "Ключи у меня"})
        self.assertEqual(send.call_args[0][:2], (901, "Сообщение · Иван"))
        self.assertEqual(send.call_args[0][3][0]["web_app"]["url"], f"https://office.example/messages/{self.admin.pk}/")
        event = Event.objects.create(title="Репетиция", date=date(2030, 1, 10), start_time=dtime(10), end_time=dtime(12), people_count=5, author=self.admin, responsible=self.member)
        event.rooms.add(Room.objects.first())
        send.reset_mock()
        self.client.post(reverse("event_status", args=[event.pk, "cancel"]))
        self.assertEqual(send.call_args[0][:2], (901, "Встреча отменена"))
        self.member.notify_events = False
        self.member.save()
        send.reset_mock()
        self.client.post(reverse("event_status", args=[event.pk, "restore"]))
        send.assert_not_called()

    def test_notification_switches_are_saved(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("profile")), "Уведомления от бота")
        self.client.post(reverse("profile_notifications"), {"notify_events": "on", "notify_requests": "on"})
        self.member.refresh_from_db()
        self.assertEqual((self.member.notify_messages, self.member.notify_events, self.member.notify_requests), (False, True, True))

    def test_send_builds_message_after_commit(self):
        with patch("accounts.telegram.call") as call, patch("threading.Thread") as thread, self.captureOnCommitCallbacks(execute=True):
            thread.side_effect = lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})()
            telegram.send(901, "Заголовок <b>", "Текст & детали", [{"text": "Открыть", "web_app": {"url": "https://office.example/"}}])
        method, payload = call.call_args[0]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["text"], "<b>Заголовок &lt;b&gt;</b>\nТекст &amp; детали")
        self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["text"], "Открыть")
