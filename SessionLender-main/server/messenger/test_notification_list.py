from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Chat, Notification


class NotificationListTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user('viewer')
        self.sender = User.objects.create_user('sender')
        self.chat = Chat.objects.create()
        self.client.force_login(self.viewer)

    def test_fifteen_messages_are_one_summary_and_preserve_unread(self):
        for i in range(15):
            Notification.objects.create(user=self.viewer, actor=self.sender, chat=self.chat, kind='message', text=str(i), is_read=i == 14)
        Notification.objects.create(user=self.viewer, actor=self.sender, kind='system', text='Separate request')
        response = self.client.get(reverse('notifications'))
        self.assertEqual(len(response.context['notifications']), 2)
        summary = next(item for item in response.context['notifications'] if item.message_count)
        self.assertEqual(summary.message_count, 15)
        self.assertFalse(summary.is_read)
        self.assertEqual(summary.unread_message_count, 14)
        self.assertContains(response, '@sender: 15 повідомлень')
        self.assertContains(response, 'Separate request')
        self.assertEqual(Notification.objects.count(), 16)
        self.client.post(reverse('notifications'))
        response = self.client.get(reverse('notifications'))
        self.assertTrue(all(item.is_read for item in response.context['notifications']))

    def test_preview_and_all_history_are_bounded_and_private(self):
        for i in range(45):
            Notification.objects.create(user=self.viewer, kind='system', text=f'Notice {i}')
        Notification.objects.create(user=self.sender, kind='system', text='Private notice')
        response = self.client.get(reverse('notifications'))
        self.assertEqual(len(response.context['notifications']), 10)
        self.assertContains(response, 'Переглянути всі')
        self.assertNotContains(response, 'Private notice')
        ids = set()
        for page in [1, 2, 3]:
            response = self.client.get(reverse('notifications'), {'all':'1', 'page':page})
            self.assertLessEqual(len(response.context['notifications']), 20)
            for item in response.context['notifications']:
                self.assertNotIn(item.pk, ids)
                ids.add(item.pk)
        self.assertEqual(len(ids), 45)

    def test_multiple_chats_from_same_sender_still_have_one_card(self):
        for chat in [self.chat, Chat.objects.create(participants_key='second-chat')]:
            Notification.objects.create(user=self.viewer, actor=self.sender, chat=chat, kind='message', text='Message')
        response = self.client.get(reverse('notifications'))
        self.assertEqual(len(response.context['notifications']), 1)
        self.assertContains(response, 'Відкрити чати')
