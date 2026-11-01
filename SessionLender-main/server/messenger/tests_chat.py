from io import BytesIO
import struct
import zlib

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from .forms import RoomForm
from .models import Chat, ChatAttachment, ChatMembership, ChatMessage, Profile

PASSWORD = 'StrongPass123!'


def make_user(username, role=Profile.ROLE_USER):
    user = User.objects.create_user(username=username, password=PASSWORD)
    user.profile.role = role
    user.profile.save(update_fields=['role'])
    return user


def image_upload(name='photo.png'):
    buffer = BytesIO()
    Image.new('RGB', (4, 4), (45, 212, 191)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def bomb_png(width=90000, height=90000):
    """PNG лише з IHDR-заголовком на width*height пікселів: сам файл ~45 байт,
    але Pillow кидатиме DecompressionBombError ще на open()."""

    def chunk(tag, payload):
        return (
            struct.pack('>I', len(payload))
            + tag
            + payload
            + struct.pack('>I', zlib.crc32(tag + payload))
        )

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IEND', b'')


class ChatAttachmentUploadTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.chat, _ = Chat.between(self.alice, self.bob)
        self.client.force_login(self.alice)
        self.url = reverse('chat-detail', args=[self.chat.pk])

    def tearDown(self):
        for attachment in ChatAttachment.objects.all():
            attachment.file.delete(save=False)

    def test_image_upload_creates_attachment_without_text(self):
        response = self.client.post(
            self.url,
            {'text': '', 'attachments': [image_upload()]},
        )
        self.assertRedirects(response, self.url)
        message = ChatMessage.objects.get()
        self.assertEqual(message.text, '')
        attachment = message.attachments.get()
        self.assertEqual(attachment.kind, ChatAttachment.KIND_IMAGE)
        self.assertEqual(attachment.original_name, 'photo.png')
        self.assertEqual(attachment.content_type, 'image/png')

    def test_voice_upload_stores_duration(self):
        voice = SimpleUploadedFile('voice.webm', b'fake-webm-data', content_type='audio/webm')
        response = self.client.post(
            self.url,
            {'text': '', 'voice': voice, 'voice_duration': '3.6'},
        )
        self.assertRedirects(response, self.url)
        attachment = ChatMessage.objects.get().attachments.get()
        self.assertEqual(attachment.kind, ChatAttachment.KIND_VOICE)
        self.assertAlmostEqual(attachment.duration_seconds, 3.6)

    def test_generic_file_upload_is_allowed(self):
        file = SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')
        self.client.post(self.url, {'text': '', 'attachments': [file]})
        attachment = ChatMessage.objects.get().attachments.get()
        self.assertEqual(attachment.kind, ChatAttachment.KIND_FILE)
        self.assertEqual(attachment.original_name, 'notes.txt')

    def test_decompression_bomb_image_becomes_error_not_500(self):
        upload = SimpleUploadedFile('bomb.png', bomb_png(), content_type='image/png')
        response = self.client.post(self.url, {'text': '', 'attachments': [upload]})
        self.assertEqual(response.status_code, 200)  # форма перемальована з помилкою, не 500
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatAttachment.objects.exists())

    def test_storage_failure_shows_message_not_500(self):
        from unittest.mock import patch
        with patch('messenger.models.ChatAttachment.save', side_effect=OSError('blob down')):
            response = self.client.post(
                self.url, {'text': 'hey', 'attachments': [image_upload()]}
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Не вдалося надіслати файл')
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatAttachment.objects.exists())

    def test_poll_fast_path_has_no_writes_when_idle(self):
        message = ChatMessage.objects.create(chat=self.chat, author=self.bob, text='hi')
        membership = ChatMembership.objects.get(chat=self.chat, user=self.alice)
        membership.last_read_at = message.created_at
        membership.save(update_fields=['last_read_at'])
        poll_url = reverse('chat-poll', args=[self.chat.pk])
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(poll_url, {'after': message.created_at.isoformat()})
        self.assertEqual(response.json()['messages'], [])
        membership.refresh_from_db()
        self.assertEqual(membership.last_read_at, message.created_at)  # idle-опитування не пише в БД
        # 2 цільових SELECT (membership+chat, остання дата) + 4 фіксовані
        # витрати автентифікованого запиту (сесія, юзер, профіль, last_seen).
        self.assertLessEqual(len(ctx.captured_queries), 6)

    def test_text_and_attachment_are_saved_together(self):
        self.client.post(
            self.url,
            {'text': 'Дивіться фото', 'attachments': [image_upload()]},
        )
        message = ChatMessage.objects.get()
        self.assertEqual(message.text, 'Дивіться фото')
        self.assertEqual(message.attachments.count(), 1)

    def test_html_file_is_rejected(self):
        file = SimpleUploadedFile('evil.html', b'<script>alert(1)</script>', content_type='text/html')
        response = self.client.post(self.url, {'text': '', 'attachments': [file]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'надсилати заборонено')
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatAttachment.objects.exists())

    def test_empty_message_is_rejected(self):
        response = self.client.post(self.url, {'text': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Додайте текст')
        self.assertFalse(ChatMessage.objects.exists())

    def test_attachment_limit_is_enforced(self):
        files = [
            SimpleUploadedFile(f'note-{index}.txt', b'data', content_type='text/plain')
            for index in range(6)
        ]
        response = self.client.post(self.url, {'text': '', 'attachments': files})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'не більше 5 файлів')
        self.assertFalse(ChatMessage.objects.exists())


class ChatAttachmentAccessTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.carol = make_user('carol')
        self.chat, _ = Chat.between(self.alice, self.bob)
        self.message = ChatMessage.objects.create(chat=self.chat, author=self.alice, text='')
        self.image = ChatAttachment.objects.create(
            message=self.message,
            file=image_upload('photo.png'),
            kind=ChatAttachment.KIND_IMAGE,
            original_name='photo.png',
            content_type='image/png',
            size=100,
        )
        self.file = ChatAttachment.objects.create(
            message=self.message,
            file=SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain'),
            kind=ChatAttachment.KIND_FILE,
            original_name='notes.txt',
            content_type='text/plain',
            size=5,
        )

    def tearDown(self):
        for attachment in ChatAttachment.objects.all():
            attachment.file.delete(save=False)

    def test_participant_can_open_attachment(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('chat-attachment', args=[self.image.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('inline', response['Content-Disposition'])
        response.close()

    def test_file_is_served_as_download(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('chat-attachment', args=[self.file.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment', response['Content-Disposition'])
        response.close()

    def test_non_participant_is_denied(self):
        self.client.force_login(self.carol)
        response = self.client.get(reverse('chat-attachment', args=[self.image.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('chat-attachment', args=[self.image.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class ChatAttachmentPollTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.chat, _ = Chat.between(self.alice, self.bob)
        self.message = ChatMessage.objects.create(chat=self.chat, author=self.alice, text='')
        self.attachment = ChatAttachment.objects.create(
            message=self.message,
            file=image_upload(),
            kind=ChatAttachment.KIND_IMAGE,
            original_name='photo.png',
            content_type='image/png',
            size=120,
        )
        self.client.force_login(self.bob)

    def tearDown(self):
        for attachment in ChatAttachment.objects.all():
            attachment.file.delete(save=False)

    def test_poll_returns_attachment_metadata(self):
        response = self.client.get(reverse('chat-poll', args=[self.chat.pk]))
        payload = response.json()
        item = payload['messages'][0]
        self.assertEqual(item['text'], '')
        self.assertEqual(item['preview'], 'Зображення')
        self.assertEqual(item['attachments'][0]['kind'], 'image')
        self.assertEqual(item['attachments'][0]['name'], 'photo.png')
        self.assertEqual(
            item['attachments'][0]['url'],
            reverse('chat-attachment', args=[self.attachment.pk]),
        )

    def test_chat_list_uses_attachment_preview(self):
        response = self.client.get(reverse('chats'))
        self.assertContains(response, 'Зображення')


class KeyboardNavigationMarkupTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.client.force_login(self.user)

    def test_base_page_contains_shortcuts_and_skip_link(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'class="skip-link"')
        self.assertContains(response, 'id="shortcutsDialog"')
        self.assertContains(response, 'data-shortcut="chats"')
        self.assertContains(response, 'aria-keyshortcuts="g m"')
        self.assertContains(response, 'Клавіатурні скорочення')

    def test_chat_has_keyboard_send_hint_and_attachment_controls(self):
        other = make_user('bob')
        chat, _ = Chat.between(self.user, other)
        response = self.client.get(reverse('chat-detail', args=[chat.pk]))
        self.assertContains(response, 'data-chat-form')
        self.assertContains(response, 'data-attachment-input')
        self.assertContains(response, 'data-voice-toggle')
        self.assertContains(response, 'enctype="multipart/form-data"')


class RoomAvatarValidationTests(TestCase):
    def test_room_avatar_bomb_is_form_error(self):
        # Django's ImageField конвертить DecompressionBombError у помилку форми — не 500.
        upload = SimpleUploadedFile('avatar.png', bomb_png(), content_type='image/png')
        form = RoomForm({'name': 'Photo room'}, {'avatar': upload})
        self.assertFalse(form.is_valid())
        self.assertIn('avatar', form.errors)

    def test_room_avatar_normal_image_passes(self):
        form = RoomForm({'name': 'Photo room'}, {'avatar': image_upload('ok.png')})
        self.assertTrue(form.is_valid(), form.errors)
