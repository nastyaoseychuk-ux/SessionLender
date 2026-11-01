from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from friendships.models import Friendship
from .forms import AddMemberForm
from .invitations import invite_to_room
from .models import Notification, Post, Room, RoomInvitation


class RoomInvitationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('inviteowner')
        cls.guest = User.objects.create_user('inviteguest')
        cls.outsider = User.objects.create_user('outsider')
        cls.room = Room.objects.create(name='Private room', created_by=cls.owner)
        cls.room.members.add(cls.owner)
        Post.objects.create(room=cls.room, author=cls.owner, caption='PRIVATE-POST-TOKEN')
        # За політикою «запрошувати можна лише друзів» owner і guest мають бути друзами.
        Friendship.objects.create(owner=cls.owner, friend=cls.guest, status=Friendship.ACCEPTED)
        Friendship.objects.create(owner=cls.guest, friend=cls.owner, status=Friendship.ACCEPTED)

    def setUp(self):
        self.client.force_login(self.guest)

    def invite(self):
        return invite_to_room(self.room, self.owner, self.guest)

    def respond(self, invitation, action, source='rooms'):
        return self.client.post(reverse('room-invitation-response', args=[invitation.pk]), {'action': action, 'source': source})

    def test_pending_blocks_private_content_and_shows_both_actions(self):
        invitation = self.invite()
        self.assertFalse(self.room.is_member(self.guest))
        self.assertEqual(self.client.get(reverse('room-detail', args=[self.room.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse('home')), 'PRIVATE-POST-TOKEN')
        self.assertEqual(Notification.objects.get(invitation=invitation).text, 'Вас запросив @inviteowner до кімнати Private room')
        for page in ['rooms', 'notifications']:
            response = self.client.get(reverse(page))
            self.assertContains(response, reverse('room-invitation-response', args=[invitation.pk]), count=2)
            self.assertContains(response, 'Прийняти')
            self.assertContains(response, 'Відхилити')

    def test_accept_from_notifications_grants_access(self):
        invitation = self.invite()
        self.assertRedirects(self.respond(invitation, 'accept', 'notifications'), reverse('notifications'))
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, RoomInvitation.ACCEPTED)
        self.assertTrue(self.room.is_member(self.guest))
        self.assertContains(self.client.get(reverse('home')), 'PRIVATE-POST-TOKEN')
        self.assertTrue(Notification.objects.get(invitation=invitation).is_read)

    def test_reject_is_final_until_reinvited(self):
        invitation = self.invite()
        self.assertRedirects(self.respond(invitation, 'reject'), reverse('rooms'))
        self.respond(invitation, 'accept')
        self.assertFalse(self.room.is_member(self.guest))
        self.assertNotContains(self.client.get(reverse('home')), 'PRIVATE-POST-TOKEN')
        self.invite()
        self.respond(invitation, 'accept')
        self.assertTrue(self.room.is_member(self.guest))

    def test_other_user_cannot_respond(self):
        invitation = self.invite()
        self.client.force_login(self.outsider)
        self.assertEqual(self.respond(invitation, 'accept').status_code, 404)
        self.assertFalse(self.room.is_member(self.guest))

    def test_post_action_and_csrf_checks(self):
        invitation = self.invite()
        url = reverse('room-invitation-response', args=[invitation.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.respond(invitation, 'invalid').status_code, 400)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.guest)
        self.assertEqual(client.post(url, {'action': 'accept'}).status_code, 403)
        self.assertFalse(self.room.is_member(self.guest))

    def test_repeat_invite_has_one_notification(self):
        self.assertEqual(self.invite().pk, self.invite().pk)
        self.assertEqual(Notification.objects.count(), 1)

    def test_create_from_card_invites_instead_of_adding(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('create-room'), {'name': 'Created together', 'invitee': self.guest.pk})
        room = Room.objects.get(name='Created together')
        self.assertTrue(room.is_member(self.owner))
        self.assertFalse(room.is_member(self.guest))
        self.assertTrue(RoomInvitation.objects.filter(room=room, user=self.guest, status='pending').exists())

    def test_add_member_form_invites(self):
        form = AddMemberForm(self.owner, {'room': self.room.pk, 'nickname': self.guest.profile.nickname})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(self.room.is_member(self.guest))
        self.assertTrue(RoomInvitation.objects.filter(room=self.room, user=self.guest).exists())

    def test_owner_only_and_existing_members_unchanged(self):
        with self.assertRaises(PermissionDenied):
            invite_to_room(self.room, self.outsider, self.guest)
        self.room.members.add(self.guest)
        self.assertIsNone(self.invite())
        self.assertTrue(self.room.is_member(self.guest))
        self.assertFalse(RoomInvitation.objects.exists())

    def test_invitation_push_is_private_and_has_fresh_id_after_reinvite(self):
        from unittest.mock import patch
        from .realtime import InboxConsumer
        invitation = self.invite()
        consumer = InboxConsumer()
        consumer.scope = {'user': self.guest}
        event = {'kind': 'room_invitation', 'id': invitation.pk}
        with patch('messenger.realtime.session_valid', return_value=True):
            first = InboxConsumer.__dict__["notification"].func(consumer, event)
            self.assertEqual(first['path'], '/messages/notifications/')
            self.assertIn('@inviteowner', first['body'])
            consumer.scope = {'user': self.outsider}
            self.assertIsNone(InboxConsumer.__dict__["notification"].func(consumer, event))
            consumer.scope = {'user': self.guest}
            self.respond(invitation, 'reject')
            self.assertIsNone(InboxConsumer.__dict__["notification"].func(consumer, event))
            self.invite()
            second = InboxConsumer.__dict__["notification"].func(consumer, event)
            self.assertNotEqual(first['id'], second['id'])

    def test_invalid_creation_preserves_invitee(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('create-room'), {'name': '', 'invitee': self.guest.pk})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, f'value="{self.guest.pk}"', status_code=400)
        self.assertContains(response, '@inviteguest', status_code=400)
        self.assertFalse(RoomInvitation.objects.exists())

    def test_inactive_or_banned_invitee_is_rejected(self):
        self.guest.is_active = False
        self.guest.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.invite()
        self.assertFalse(RoomInvitation.objects.exists())
