from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from friendships.models import Friendship

from .models import Room, RoomInvitation


class RoomInviteeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('roomowner')
        cls.invitee = User.objects.create_user('roomguest')
        cls.banned = User.objects.create_user('bannedguest')
        cls.banned.profile.is_banned = True
        cls.banned.profile.save(update_fields=['is_banned'])
        # Політика: запрошувати до кімнати можна лише друзів.
        Friendship.objects.create(owner=cls.owner, friend=cls.invitee, status=Friendship.ACCEPTED)
        Friendship.objects.create(owner=cls.invitee, friend=cls.owner, status=Friendship.ACCEPTED)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_person_card_preserves_selected_user(self):
        self.owner.profile.role = 'admin'
        self.owner.profile.save(update_fields=['role'])
        response = self.client.get(reverse('people'))
        # Кнопка «Запросити» тепер відкриває JS-пікер вибору кімнати.
        self.assertContains(response, 'data-room-invite-open')
        self.assertContains(response, f'data-user-id="{self.invitee.pk}"')
        response = self.client.get(reverse('rooms'), {'invitee': self.invitee.pk})
        self.assertContains(response, f'value="{self.invitee.pk}"')
        self.assertContains(response, '@roomguest')

    def test_creates_room_and_pending_invitation(self):
        response = self.client.post(reverse('create-room'), {
            'name': 'Our room', 'invitee': self.invitee.pk,
        })
        room = Room.objects.get(name='Our room')
        self.assertRedirects(response, reverse('room-detail', args=[room.pk]))
        self.assertSetEqual(set(room.members.values_list('pk', flat=True)), {self.owner.pk})
        self.assertTrue(RoomInvitation.objects.filter(room=room, user=self.invitee, status=RoomInvitation.PENDING).exists())

    def test_normal_room_creation_still_works(self):
        self.client.post(reverse('create-room'), {'name': 'My room'})
        self.assertSetEqual(set(Room.objects.get().members.values_list('pk', flat=True)), {self.owner.pk})

    def test_validation_preserves_invitee(self):
        response = self.client.post(reverse('create-room'), {'name': '', 'invitee': self.invitee.pk})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, f'value="{self.invitee.pk}"', status_code=400)
        self.assertFalse(Room.objects.exists())

    def test_invalid_or_banned_invitee_cannot_create_partial_room(self):
        for invitee in ['wrong', '99999999', str(self.banned.pk)]:
            with self.subTest(invitee=invitee):
                response = self.client.post(reverse('create-room'), {'name': 'Room', 'invitee': invitee})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(Room.objects.exists())
