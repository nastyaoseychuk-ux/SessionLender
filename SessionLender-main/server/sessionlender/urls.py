from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .about import project_about
from messenger import health
from messenger.desktop_api import desktop_session, desktop_avatar
from messenger.desktop_stream import desktop_events

urlpatterns = [
    path('health/', health.health_check, name='health'),
    path('healthz/', health.health_check, name='healthz'),
    path('desktop/events/', desktop_events, name='desktop-events'),
    path('desktop/avatar/<int:user_id>/', desktop_avatar, name='desktop-avatar'),
    path('desktop/session/', desktop_session, name='desktop-session'),
    path('about/', project_about, name='about'),
    path('admin/', admin.site.urls),
    path('', include('messenger.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = 'messenger.views.error_403'
handler404 = 'messenger.views.error_404'
