from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from datetime import timedelta
from django.utils import timezone
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from .desktop_api import token_hash
from .desktop_models import DesktopTicket
from .desktop_auth import DesktopTicketMiddleware


class DesktopSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('desktop', password='test-password')
        self.url = reverse('desktop-session')

    def test_login_and_post_required(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_ticket_is_bound_to_current_session(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        data = response.json()
        stored = DesktopTicket.objects.get(token_hash=token_hash(data['ticket']))
        self.assertEqual(stored.session_id, self.client.session.session_key)
        self.assertNotIn(self.client.session.session_key, data['ticket'])
        self.assertEqual(data['account'], str(self.user.pk))
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url).status_code, 403)

    def test_banned_user_cannot_get_ticket(self):
        self.client.force_login(self.user)
        self.user.profile.is_banned = True
        self.user.profile.save()
        self.assertNotEqual(self.client.post(self.url).status_code, 200)

    def call_middleware(self, path, authorization):
        messages = []
        scopes = []
        async def app(scope, receive, send):
            scopes.append(scope)
        async def receive():
            return {'type': 'websocket.connect'}
        async def send(message):
            messages.append(message)
        async_to_sync(DesktopTicketMiddleware(app))(
            {'type': 'websocket', 'path': path, 'headers': [(b'authorization', authorization)]},
            receive, send,
        )
        return messages, scopes

    def test_ticket_only_works_for_inbox(self):
        ticket = 't' * 43
        session = Session.objects.create(session_key='a' * 32, session_data='', expire_date=timezone.now()+timedelta(hours=1))
        DesktopTicket.objects.create(session=session, token_hash=token_hash(ticket), expires_at=timezone.now()+timedelta(hours=1))
        messages, scopes = self.call_middleware('/ws/inbox/', ('Bearer ' + ticket).encode())
        self.assertFalse(messages)
        self.assertIn((b'cookie', b'sessionid=' + b'a' * 32), scopes[0]['headers'])
        messages, scopes = self.call_middleware('/ws/chat/1/', ('Bearer ' + ticket).encode())
        self.assertEqual(messages[0]['code'], 4403)
        self.assertFalse(scopes)

    def test_tampered_ticket_is_rejected(self):
        messages, scopes = self.call_middleware('/ws/inbox/', b'Bearer invalid')
        self.assertEqual(messages[0]['code'], 4403)
        self.assertFalse(scopes)

    def test_expired_or_logged_out_session_is_rejected(self):
        self.client.force_login(self.user)
        ticket = self.client.post(self.url).json()['ticket']
        DesktopTicket.objects.filter(token_hash=token_hash(ticket)).update(expires_at=timezone.now()-timedelta(seconds=1))
        messages, scopes = self.call_middleware('/ws/inbox/', ('Bearer '+ticket).encode())
        self.assertEqual(messages[0]['code'], 4403)
        self.assertFalse(scopes)
        fresh_ticket = self.client.post(self.url).json()['ticket']
        self.client.logout()
        messages, scopes = self.call_middleware('/ws/inbox/', ('Bearer '+fresh_ticket).encode())
        self.assertEqual(messages[0]['code'], 4403)
        self.assertFalse(scopes)

    def test_avatar_requires_restricted_key_and_rejects_logout(self):
        from unittest.mock import patch
        from django.http import HttpResponse
        self.client.force_login(self.user)
        ticket = self.client.post(self.url).json()['ticket']
        target = reverse('desktop-avatar', args=[self.user.pk])
        anonymous = Client()
        self.assertEqual(anonymous.get(target).status_code, 401)
        with patch('messenger.send_api.avatar', return_value=HttpResponse('image')):
            response = anonymous.get(target, HTTP_AUTHORIZATION='Bearer '+ticket)
            self.assertEqual(response.status_code, 200)
        self.client.logout()
        self.assertEqual(anonymous.get(target, HTTP_AUTHORIZATION='Bearer '+ticket).status_code, 403)

    def test_notification_identity_has_nickname_and_private_avatar_route(self):
        from .realtime import InboxConsumer
        from .models import Room
        profile = self.user.profile
        profile.avatar = 'avatars/example.webp'
        profile.save(update_fields=['avatar'])
        room = Room.objects.create(name='Studio', created_by=self.user)
        consumer = InboxConsumer()
        identity = consumer.notification_identity('room', room.pk)
        self.assertEqual(identity['nickname'], '@desktop')
        self.assertEqual(identity['avatar'], f'/desktop/avatar/{self.user.pk}/')
