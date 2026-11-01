"""Public project page, independent of account data."""

import os

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

SLIDE_COUNT = 4
DEFAULT_GITHUB_URL = "https://github.com/nastyaoseychuk-ux"  


def get_about_context():
    """Keep image paths and external links in one place."""
    return {
        "slides": [
            {
                "dark": f"about/dark-{number}.webp",
                "light": f"about/light-{number}.webp",
            }
            for number in range(1, SLIDE_COUNT + 1)
        ],
        "android_url": settings.ANDROID_DOWNLOAD_URL,
        "desktop_url": settings.DESKTOP_DOWNLOAD_URL,
        "github_url": os.environ.get("PROJECT_GITHUB_URL", DEFAULT_GITHUB_URL),
    }


def project_about(request):
    # No RequestContext: private profile/unread processors would query the DB.
    html = render_to_string("about.html", get_about_context())
    return HttpResponse(html)
