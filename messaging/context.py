def unread_messages(request):
    if not request.user.is_authenticated or request.user.must_change_password:
        return {"unread_message_count": 0}
    return {"unread_message_count": request.user.received_messages.filter(read_at__isnull=True).count()}
