from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from friendships.models import Friendship
from .invitations import invite_to_room
from .models import Room, RoomInvitation, Notification, Profile

class InvitationPermissionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('inv-owner')
        self.target = User.objects.create_user('inv-target')
        self.room = Room.objects.create(name='Private', created_by=self.owner)
        self.room.members.add(self.owner)
        self.client.force_login(self.owner)

    def test_nonfriend_and_following_cannot_invite(self):
        for status in [None, Friendship.PENDING, Friendship.REJECTED]:
            Friendship.objects.all().delete()
            if status:
                Friendship.objects.create(owner=self.owner, friend=self.target, status=status)
            with self.assertRaises(PermissionDenied):
                invite_to_room(self.room, self.owner, self.target)
        self.assertFalse(RoomInvitation.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_accepted_friend_can_be_invited(self):
        Friendship.objects.create(owner=self.owner, friend=self.target, status=Friendship.ACCEPTED)
        invitation = invite_to_room(self.room, self.owner, self.target)
        self.assertEqual(invitation.status, RoomInvitation.PENDING)
        self.assertFalse(self.room.is_member(self.target))

    def test_admin_can_invite_nonfriend(self):
        self.owner.profile.role = Profile.ROLE_ADMIN
        self.owner.profile.save(update_fields=['role'])
        self.assertIsNotNone(invite_to_room(self.room, self.owner, self.target))

    def test_analyst_cannot_invite_nonfriend(self):
        self.owner.profile.role = Profile.ROLE_ANALYST
        self.owner.profile.save(update_fields=['role'])
        with self.assertRaises(PermissionDenied):
            invite_to_room(self.room, self.owner, self.target)

    def test_post_cannot_bypass_permission(self):
        response = self.client.post(reverse('add-member-from-people'), {'room':self.room.pk, 'nickname':self.target.username})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RoomInvitation.objects.exists())

    def test_create_with_unapproved_invitee_rolls_back(self):
        response = self.client.post(reverse('create-room'), {'name':'No bypass','invitee':self.target.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Room.objects.filter(name='No bypass').exists())

    def test_profile_button_disabled_until_accepted(self):
        Friendship.objects.create(owner=self.owner, friend=self.target, status=Friendship.PENDING)
        url = reverse('user-profile', args=[self.target.profile.nickname])
        html = self.client.get(url).content.decode()
        self.assertIn('visibility:hidden!important;opacity:0!important;pointer-events:none!important;user-select:none', html)
        Friendship.objects.filter(owner=self.owner).update(status=Friendship.ACCEPTED)
        html = self.client.get(url).content.decode()
        self.assertNotIn('visibility:hidden!important;opacity:0!important;pointer-events:none!important;user-select:none', html)

    def test_picker_uses_avatar_buttons_instead_of_room_select(self):
        Friendship.objects.create(owner=self.owner, friend=self.target, status=Friendship.ACCEPTED)
        response = self.client.get(reverse('friends'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('<select name="room"', html)
        self.assertIn('data-room-invite-picker', html)
        self.assertIn('name="room" value="%s"' % self.room.pk, html)
        self.assertIn('data-nickname="inv-target"', html)

    def test_admin_friends_page_hides_following_invite(self):
        from html.parser import HTMLParser
        class Buttons(HTMLParser):
            def __init__(self):
                super().__init__(); self.targets = []
            def handle_starttag(self, tag, attrs):
                data = dict(attrs)
                if tag == "button" and "data-room-invite-open" in data:
                    self.targets.append(data.get("data-user-id"))
        self.owner.profile.role = Profile.ROLE_ADMIN
        self.owner.profile.save(update_fields=['role'])
        Friendship.objects.create(owner=self.owner, friend=self.target, status=Friendship.PENDING)
        response = self.client.get(reverse('friends'))
        buttons = Buttons(); buttons.feed(response.content.decode())
        self.assertNotIn(str(self.target.pk), buttons.targets)
        self.assertIn('visibility:hidden!important', response.content.decode())
        response = self.client.get(reverse('people'))
        buttons = Buttons(); buttons.feed(response.content.decode())
        self.assertIn(str(self.target.pk), buttons.targets)
