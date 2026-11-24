import hashlib
import json

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

# Цвет фона и панели совпадает с bg/canvas светлой темы в макете.
CANVAS = "#f2f2f5"


@require_GET
@cache_control(public=True, max_age=60 * 60)
def manifest(request):
    data = {
        "id": "/",
        "name": "Наш офис",
        "short_name": "Наш офис",
        "description": "Бронирование помещений офиса New Territory",
        "lang": "ru",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": CANVAS,
        "theme_color": CANVAS,
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/manifest+json; charset=utf-8")


# Service worker (макеты PWA 14 «Офлайн» и 15 «Новая версия»).
# Статика кэшируется заранее; страницы из этого списка сохраняются после каждого открытия,
# чтобы без сети показать последнее расписание. Формы, вход и управление не сохраняются.
PRECACHE = ["app.css", "app.js", "pwa.js", "event-form.js", "messages.js", "icons.svg", "favicon.svg", "icons/icon-192.png", "icons/apple-touch-icon.png"]
OFFLINE_PAGES = [r"^/$", r"^/events/\d+/$", r"^/events/cancelled/$", r"^/messages/$", r"^/messages/\d+/$", r"^/profile/$"]


def _version(urls):
    digest = hashlib.sha256()
    for name, url in zip(PRECACHE, urls):
        digest.update(url.encode())
        if settings.DEBUG:  # без манифеста адреса не меняются — учитываем содержимое
            path = finders.find(name)
            if path:
                with open(path, "rb") as source:
                    digest.update(source.read())
    return digest.hexdigest()[:12]


@require_GET
def service_worker(request):
    urls = [static(name) for name in PRECACHE]
    config = {
        "version": _version(urls),
        "precache": urls,
        "immutable": urls[0] != settings.STATIC_URL + PRECACHE[0],  # адреса с хэшем — файл не меняется
        "static": settings.STATIC_URL,
        "home": reverse("home"),
        "logout": reverse("logout"),
        "pages": OFFLINE_PAGES,
        "css": static("app.css"),
        "logo": static("favicon.svg"),
    }
    body = render_to_string("pwa/sw.js", {"config": mark_safe(json.dumps(config, ensure_ascii=False))})
    response = HttpResponse(body, content_type="text/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response
