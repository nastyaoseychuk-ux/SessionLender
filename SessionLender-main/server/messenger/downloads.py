"""Choose the download link for browser visitors; native clients hide the button."""

import re

from django.conf import settings

MOBILE_DEVICE = re.compile(r"android|iphone|ipad|ipod|mobile", re.IGNORECASE)


def application_download(request):
    user_agent = request.headers.get("User-Agent", "")
    # The marker identifies our app; wv also covers older Android WebView builds.
    is_app = "SessionLenderAndroid/" in user_agent or (
        "Android" in user_agent and "; wv)" in user_agent
    )
    if is_app:
        return {"app_download": None}

    is_mobile = (
        request.headers.get("Sec-CH-UA-Mobile") == "?1"
        or MOBILE_DEVICE.search(user_agent) is not None
    )
    return {
        "app_download": {
            "url": (
                settings.ANDROID_DOWNLOAD_URL
                if is_mobile
                else settings.DESKTOP_DOWNLOAD_URL
            ),
            "label": "Завантажити додаток",
            "title": (
                "Завантажити Android-додаток (APK)"
                if is_mobile
                else "Завантажити тестовий додаток для ПК (EXE)"
            ),
        }
    }
