from django.conf import settings
from .urls import urlpatterns as original
urlpatterns = list(original)
if getattr(settings, 'LOCAL', False):
    from django.urls import re_path
    from django.views.static import serve
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
