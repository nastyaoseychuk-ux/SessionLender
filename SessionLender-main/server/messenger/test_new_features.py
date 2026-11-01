from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from .audit import log_event
from .models import AuditEvent, Chat, ChatMessage, Notification, Profile


class HealthCheckTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'db': 'ok'})


class ChatsNPlusOneTests(TestCase):
    def test_query_count_is_constant_regardless_of_chat_count(self):
        owner = User.objects.create_user(username='inboxowner')
        self.client.force_login(owner)
        for i in range(30):
            peer = User.objects.create_user(username=f'peer{i}')
            chat, _ = Chat.between(owner, peer)
            for j in range(3):
                ChatMessage.objects.create(chat=chat, author=peer, text=f'p{j}')

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse('chats'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['entries']), 30)
        # N+1 would scale ~3 queries per chat (>90). Constant path stays flat.
        self.assertLessEqual(len(ctx.captured_queries), 15)


class AuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='audituser')

    def test_log_event_stores_fields(self):
        event = log_event(
            AuditEvent.ACTION_MESSAGE_DELETED,
            actor=self.user,
            target='chat-1',
            detail='test delete',
            request=None,
        )
        self.assertEqual(event.action, AuditEvent.ACTION_MESSAGE_DELETED)
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.target, 'chat-1')
        self.assertTrue(AuditEvent.objects.filter(action=AuditEvent.ACTION_LOGIN_SUCCESS).count() == 0)

    def test_login_success_event(self):
        log_event(AuditEvent.ACTION_LOGIN_SUCCESS, actor=self.user, target=f'@{self.user.username}')
        self.assertTrue(AuditEvent.objects.filter(action=AuditEvent.ACTION_LOGIN_SUCCESS).exists())


class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='notifuser')
        self.client.force_login(self.user)

    def test_notifications_page_paginates(self):
        for i in range(60):
            Notification.objects.create(
                user=self.user, kind=Notification.KIND_MESSAGE, text=f'n{i}'
            )
        response = self.client.get(reverse('notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['notifications']), 10)
        self.assertTrue(response.context['page_obj'].has_next())

    def test_mark_all_read(self):
        Notification.objects.create(
            user=self.user, kind=Notification.KIND_MESSAGE, text='hello', is_read=False,
        )
        response = self.client.post(reverse('notifications'))
        self.assertRedirects(response, reverse('notifications'))
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)

    def test_clear_old_via_view(self):
        old = Notification.objects.create(user=self.user, kind=Notification.KIND_MESSAGE, text='old')
        new = Notification.objects.create(user=self.user, kind=Notification.KIND_MESSAGE, text='new')
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        response = self.client.post(reverse('notifications'), {'action': 'clear_old'})
        self.assertRedirects(response, reverse('notifications'))
        self.assertEqual(list(Notification.objects.values_list('pk', flat=True)), [new.pk])

    def test_clear_old_command(self):
        other = User.objects.create_user(username='otheruser')
        old = Notification.objects.create(user=other, kind=Notification.KIND_MESSAGE, text='old')
        Notification.objects.create(user=other, kind=Notification.KIND_MESSAGE, text='new')
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=45)
        )
        call_command('cleanup_notifications', days=30)
        self.assertFalse(Notification.objects.filter(pk=old.pk).exists())
