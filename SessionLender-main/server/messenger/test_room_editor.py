import io
import tempfile
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from .models import Room, Post


class RoomEditorTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.owner = User.objects.create_user('owner', password='test-password')
        self.member = User.objects.create_user('member', password='test-password')
        self.room = Room.objects.create(name='Original', created_by=self.owner)
        self.room.members.add(self.owner, self.member)
        self.client.force_login(self.owner)

    def photo(self):
        data = io.BytesIO()
        Image.new('RGB', (20, 20)).save(data, 'PNG')
        return SimpleUploadedFile('room.png', data.getvalue(), content_type='image/png')

    def test_create_with_avatar(self):
        response = self.client.post(reverse('create-room'), {'name':'Photo room', 'avatar':self.photo()})
        self.assertEqual(response.status_code, 302)
        room = Room.objects.get(name='Photo room')
        self.assertTrue(room.avatar.name.startswith('room_avatars/'))
        self.assertTrue(room.avatar.storage.exists(room.avatar.name))

    def test_edit_and_preserve_avatar_without_new_upload(self):
        url = reverse('edit-room', args=[self.room.pk])
        self.assertContains(self.client.get(url), 'Вибрати аватар кімнати')
        response = self.client.post(url, {'name':'Changed', 'description':'New description', 'avatar':self.photo()})
        self.assertEqual(response.status_code, 302)
        self.room.refresh_from_db()
        saved = self.room.avatar.name
        self.client.post(url, {'name':'Again', 'description':''})
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, 'Again')
        self.assertEqual(self.room.avatar.name, saved)

    def test_member_cannot_edit_or_see_edit_button(self):
        self.client.force_login(self.member)
        url = reverse('edit-room', args=[self.room.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'name':'Hacked'}).status_code, 403)
        self.assertNotContains(self.client.get(reverse('room-detail', args=[self.room.pk])), url)

    def test_invalid_image_and_blank_name_rejected(self):
        url = reverse('edit-room', args=[self.room.pk])
        response = self.client.post(url, {'name':'Wrong', 'avatar':SimpleUploadedFile('bad.png', b'not an image')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(url, {'name':''}).status_code, 400)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, 'Original')

    def test_newest_post_first_and_edit_button(self):
        old = Post.objects.create(room=self.room, author=self.owner, caption='older')
        new = Post.objects.create(room=self.room, author=self.owner, caption='newer')
        response = self.client.get(reverse('room-detail', args=[self.room.pk]))
        self.assertEqual(list(response.context['posts']), [new, old])
        self.assertContains(response, reverse('edit-room', args=[self.room.pk]))

    def test_feed_shows_room_avatar_in_both_lists(self):
        self.room.avatar = self.photo()
        self.room.save()
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.room.avatar.url, count=2)

    def test_feed_without_room_avatar_keeps_initials(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OR</span>', count=2)

    def test_private_room_image_requires_membership(self):
        self.room.avatar = self.photo()
        self.room.save()
        url = reverse('private-media', kwargs={'name': self.room.avatar.name})
        allowed = self.client.get(url)
        try:
            self.assertEqual(allowed.status_code, 200)
        finally:
            allowed.close()  # на Windows відкритий handle блокує cleanup TemporaryDirectory
        outsider = User.objects.create_user('private-outsider')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
