from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Chat, Room
from .security import is_rate_limited, is_rate_limited_identity


class ThrottleUnitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_window_allows_limit_hits(self):
        self.assertFalse(is_rate_limited(None, 'unit', limit=2, window_seconds=60))
        self.assertFalse(is_rate_limited(None, 'unit', limit=2, window_seconds=60))

    def test_exceeding_limit_blocks(self):
        self.assertFalse(is_rate_limited(None, 'unit', limit=2, window_seconds=60))
        self.assertFalse(is_rate_limited(None, 'unit', limit=2, window_seconds=60))
        self.assertTrue(is_rate_limited(None, 'unit', limit=2, window_seconds=60))

    def test_scopes_are_isolated(self):
        for _ in range(3):
            is_rate_limited_identity('u1', 'scope-a', limit=2, window_seconds=60)
        self.assertTrue(is_rate_limited_identity('u1', 'scope-a', limit=2, window_seconds=60))
        self.assertFalse(is_rate_limited_identity('u1', 'scope-b', limit=2, window_seconds=60))

    def test_identities_are_isolated(self):
        for _ in range(3):
            is_rate_limited_identity('u1', 'scope', limit=2, window_seconds=60)
        self.assertFalse(is_rate_limited_identity('u2', 'scope', limit=2, window_seconds=60))


@override_settings(TEST=False, ROOM_CREATE_RATE_LIMIT=1)
class ThrottleViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='throttleuser', password='pass1234!')
        self.client.force_login(self.user)

    def test_room_create_blocked_after_limit(self):
        first = self.client.post(
            reverse('create-room'), {'name': 'Room A', 'description': ''}
        )
        self.assertEqual(first.status_code, 302)
        self.assertTrue(Room.objects.filter(name='Room A').exists())
        second = self.client.post(
            reverse('create-room'), {'name': 'Room B', 'description': ''}
        )
        self.assertEqual(second.status_code, 302)
        self.assertFalse(Room.objects.filter(name='Room B').exists())


@override_settings(TEST=False, MESSAGE_RATE_LIMIT=1)
class ChatMessageThrottleViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(username='alice2')
        self.bob = User.objects.create_user(username='bob2')
        self.client.force_login(self.alice)
        self.chat, _ = Chat.between(self.alice, self.bob)

    def test_message_blocked_after_limit(self):
        url = reverse('chat-detail', args=[self.chat.pk])
        first = self.client.post(url, {'text': 'one'})
        self.assertEqual(first.status_code, 302)
        second = self.client.post(url, {'text': 'two'})
        self.assertEqual(second.status_code, 302)
        self.assertFalse(self.chat.messages.filter(text='two').exists())
        self.assertEqual(self.chat.messages.count(), 1)
