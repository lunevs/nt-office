from django.urls import path
from accounts import views
from bookings import views as bookings
from messaging import views as messaging
from . import pwa
from accounts import tg_views as tg
urlpatterns = [
    path("manifest.webmanifest", pwa.manifest, name="manifest"),
    path("sw.js", pwa.service_worker, name="service_worker"),
    path("messages/", messaging.inbox, name="messages"),
    path("messages/people/", messaging.people, name="message_people"),
    path("messages/<int:pk>/", messaging.thread, name="message_thread"),
    path("messages/<int:pk>/updates/", messaging.updates, name="message_updates"),
    path("messages/<int:pk>/read/", messaging.mark_read, name="message_read"),
    path("", bookings.calendar, name="home"),
    path("events/cancelled/", bookings.cancelled, name="events_cancelled"),
    path("events/<int:pk>/status/<str:action>/", bookings.change_status, name="event_status"),
    path("api/events/<int:pk>/", bookings.event_data, name="event_data"),
    path("events/new/", bookings.create, name="event_create"),
    path("events/<int:pk>/", bookings.detail, name="event_detail"),
    path("events/<int:pk>/edit/", bookings.edit, name="event_edit"),
    path("events/<int:pk>/key/", bookings.key_handled, name="event_key_handled"),
    path("healthz/", views.health, name="health"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/<str:field>/", views.profile_edit, name="profile_edit"),
    path("password/", views.password_change, name="password_change"),
    path("management/", views.users, name="users"),
    path("management/<int:pk>/access/<str:action>/", views.user_access, name="user_access"),
    path("management/<int:pk>/reset-password/", views.reset_password, name="reset_password"),
    path("management/<int:pk>/role/", views.user_role, name="user_role"),
    path("verification/request/", tg.request_verification, name="request_verification"),
    path("tg/", tg.entry, name="telegram_entry"),
    path("telegram/auth/", tg.webapp_auth, name="telegram_auth"),
    path("telegram/login/", tg.widget_login, name="telegram_login"),
    path("telegram/callback/", tg.callback, name="telegram_callback"),
    path("telegram/join/", tg.join, name="telegram_join"),
    path("telegram/link/", tg.link, name="telegram_link"),
    path("telegram/unlink/", tg.unlink, name="telegram_unlink"),
    path("telegram/webhook/", tg.webhook, name="telegram_webhook"),
    path("profile/notifications/", tg.notifications, name="profile_notifications"),
]
