"""Make the current user's unread message count available to every template."""


def unread_messages(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_messages": 0}
    return {"unread_messages": user.app_messages.filter(read_at__isnull=True).count()}
