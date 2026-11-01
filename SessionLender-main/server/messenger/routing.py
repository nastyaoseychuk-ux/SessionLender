from django.urls import re_path

from .realtime import ChatConsumer, InboxConsumer

websocket_urlpatterns = [
    re_path(r'^ws/inbox/$', InboxConsumer.as_asgi()),
    re_path(r'^ws/chat/(?P<chat_id>\d+)/$', ChatConsumer.as_asgi()),
    re_path(r'^ws/chats/(?P<chat_id>\d+)/$', ChatConsumer.as_asgi()),
]
