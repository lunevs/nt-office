from django.urls import path
from accounts import views
from bookings import views as bookings
from messaging import views as messaging
urlpatterns = [
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
    path("healthz/", views.health, name="health"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register, name="register"),
    path("pending/", views.pending, name="pending"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("profile/edit/<str:field>/", views.profile_edit, name="profile_edit"),
    path("password/", views.password_change, name="password_change"),
    path("management/", views.users, name="users"),
    path("management/<int:pk>/activate/", views.activate, name="activate"),
    path("management/<int:pk>/reset-password/", views.reset_password, name="reset_password"),
]
