from django.conf import settings


class FrameAncestorsMiddleware:
    """Кому можно встраивать страницы во фрейм (CSP frame-ancestors). Заменяет X-Frame-Options: DENY,
    потому что Telegram Web открывает мини-приложение во фрейме web.telegram.org."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", f"frame-ancestors {settings.FRAME_ANCESTORS}")
        return response
