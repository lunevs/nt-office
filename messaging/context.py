def unread_messages(request):
    from accounts.telegram import oauth_url
    in_telegram = request.session.get("in_telegram", False)
    context = {"in_telegram": in_telegram, "telegram_oauth_url": None if in_telegram else oauth_url(request)}
    if not request.user.is_authenticated or request.user.must_change_password:
        return {**context, "unread_message_count": 0}
    context["unread_message_count"] = request.user.received_messages.filter(read_at__isnull=True).count()
    if request.user.is_administrator:
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from bookings.models import Event
        requests = get_user_model().objects.filter(is_active=True, verified=False, verification_requested_at__isnull=False).count()
        keys = Event.objects.filter(key_needed=True, key_handled=False, status=Event.Status.ACTIVE, date__gte=timezone.localdate()).count()
        context["pending_requests_count"] = requests + keys
    return context
