"""Exercise real HTTP sends through the authenticated live delivery endpoints."""
import json
import uuid

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse

from .desktop_stream import desktop_events
from .models import Chat


@override_settings(
    ALLOWED_HOSTS=['testserver'],
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}},
)
class DesktopDeliveryTests(TransactionTestCase):
    def setUp(self):
        self.sender = User.objects.create_user('sender')
        self.reader = User.objects.create_user('reader')
        self.chat, _ = Chat.between(self.sender, self.reader)
        self.sender_client = Client()
        self.sender_client.force_login(self.sender)
        recipient = Client()
        recipient.force_login(self.reader)
        self.ticket = recipient.post(reverse('desktop-session')).json()['ticket']

    async def send_message(self):
        response = await database_sync_to_async(self.sender_client.post)(
            reverse('chat-send-api', args=[self.chat.pk]),
            data=json.dumps({'text': 'Live delivery test', 'client_nonce': str(uuid.uuid4())}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def assert_notice(self, notice):
        self.assertEqual(notice['type'], 'notification')
        self.assertEqual(notice['body'], 'Live delivery test')
        self.assertEqual(notice['nickname'], '@sender')
        self.assertEqual(notice['path'], f'/messages/{self.chat.pk}/')

    def test_http_send_reaches_authenticated_websocket(self):
        async_to_sync(self.websocket_scenario)()

    async def websocket_scenario(self):
        from sessionlender.asgi import application
        connection = ApplicationCommunicator(application, {
            'type': 'websocket', 'path': '/ws/inbox/', 'scheme': 'ws',
            'query_string': b'', 'subprotocols': [],
            'headers': [(b'origin', b'http://testserver'),
                        (b'authorization', ('Bearer ' + self.ticket).encode())],
            'client': ('127.0.0.1', 1234), 'server': ('testserver', 80),
        })
        await connection.send_input({'type': 'websocket.connect'})
        accepted = await connection.receive_output(timeout=3)
        self.assertEqual(accepted['type'], 'websocket.accept')
        await connection.receive_output(timeout=3)  # Initial unread count.
        await self.send_message()
        for _ in range(5):
            frame = await connection.receive_output(timeout=3)
            notice = json.loads(frame['text'])
            if notice['type'] == 'notification':
                self.assert_notice(notice)
                break
        else:
            self.fail('No message notification')
        await connection.send_input({'type': 'websocket.disconnect', 'code': 1000})
        await connection.wait(timeout=3)

    def test_http_send_reaches_authenticated_event_stream(self):
        async_to_sync(self.stream_scenario)()

    async def stream_scenario(self):
        request = RequestFactory().get(
            '/desktop/events/', HTTP_AUTHORIZATION='Bearer ' + self.ticket,
        )
        response = await desktop_events(request)
        self.assertEqual(response.status_code, 200)
        iterator = response._iterator
        ready = await anext(iterator)
        self.assertIn('ready', ready)
        await self.send_message()
        frame = await anext(iterator)
        notice = json.loads(frame.removeprefix('data: ').strip())
        self.assert_notice(notice)
        await iterator.aclose()
