from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import AppSettings, AuditEvent, Chat, ChatMembership, ChatMessage, Profile, Room


def make_user(username):
    user = User.objects.create_user(username=username)
    Profile.for_user(user)
    return user


class GroupChatTests(TestCase):
    def setUp(self):
        self.owner = make_user('groupowner')
        self.member = make_user('groupmember')
        self.outsider = make_user('groupoutsider')
        self.client.force_login(self.owner)

    def test_group_chat_member_can_post(self):
        chat = Chat.create_group(self.owner, 'Group A', [self.member])
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('chat-detail', args=[chat.pk]),
            {'text': 'hi group'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ChatMessage.objects.filter(chat=chat).exists())

    def test_create_group_writes_audit_event(self):
        response = self.client.post(
            reverse('create-group-chat'),
            {'title': 'Team X', 'members': [str(self.member.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        chat = Chat.objects.get(title='Team X')
        self.assertEqual(chat.kind, Chat.KIND_GROUP)
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditEvent.ACTION_GROUP_CREATED, actor=self.owner
            ).exists()
        )
        self.assertEqual(
            set(chat.memberships.values_list('user_id', flat=True)),
            {self.owner.pk, self.member.pk},
        )

    def test_create_group_requires_title_and_member(self):
        response = self.client.post(reverse('create-group-chat'), {'title': '', 'members': []})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Chat.objects.filter(kind=Chat.KIND_GROUP).exists())

    def test_create_group_with_multiple_members(self):
        third = make_user('groupthird')
        response = self.client.post(
            reverse('create-group-chat'),
            {'title': 'Many', 'members': [str(self.member.pk), str(third.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        chat = Chat.objects.get(title='Many')
        self.assertEqual(
            set(chat.memberships.values_list('user_id', flat=True)),
            {self.owner.pk, self.member.pk, third.pk},
        )

    def test_outsider_cannot_open_group(self):
        chat = Chat.create_group(self.owner, 'Private Group', [self.member])
        self.client.force_login(self.outsider)
        response = self.client.get(reverse('chat-detail', args=[chat.pk]))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_add_member(self):
        chat = Chat.create_group(self.owner, 'Group B', [self.member])
        response = self.client.post(
            reverse('add-chat-member', args=[chat.pk]),
            {'nickname': Profile.for_user(self.outsider).nickname},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChatMembership.objects.filter(chat=chat, user=self.outsider).exists())
        self.assertTrue(
            AuditEvent.objects.filter(action=AuditEvent.ACTION_GROUP_MEMBER_ADDED).exists()
        )

    def test_member_cannot_add_others(self):
        chat = Chat.create_group(self.owner, 'Group C', [self.member])
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('add-chat-member', args=[chat.pk]),
            {'nickname': Profile.for_user(self.outsider).nickname},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_be_removed(self):
        chat = Chat.create_group(self.owner, 'Group D', [self.member])
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('remove-chat-member', args=[chat.pk, self.owner.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChatMembership.objects.filter(chat=chat, user=self.owner).exists())

    def test_only_owner_can_delete_group(self):
        chat = Chat.create_group(self.owner, 'Group E', [self.member])
        self.client.force_login(self.member)
        response = self.client.post(reverse('delete-group-chat', args=[chat.pk]))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('delete-group-chat', args=[chat.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Chat.objects.filter(pk=chat.pk).exists())

    def test_member_can_leave_group(self):
        chat = Chat.create_group(self.owner, 'Group F', [self.member])
        self.client.force_login(self.member)
        response = self.client.post(reverse('leave-chat', args=[chat.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChatMembership.objects.filter(chat=chat, user=self.member).exists())


class RoomGroupTests(TestCase):
    def setUp(self):
        self.owner = make_user('roomowner')
        self.member = make_user('roommember')
        self.second = make_user('roomsecond')
        self.outsider = make_user('roomoutsider')
        self.room = Room.objects.create(name='Design', created_by=self.owner)
        self.room.members.set([self.owner, self.member, self.second])

    def test_member_creates_group_with_all_room_members(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('create-room-group', args=[self.room.pk]))
        self.assertEqual(response.status_code, 302)
        chat = Chat.objects.get(kind=Chat.KIND_GROUP)
        self.assertEqual(chat.title, 'Design')
        self.assertEqual(
            set(chat.memberships.values_list('user_id', flat=True)),
            {self.owner.pk, self.member.pk, self.second.pk},
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action=AuditEvent.ACTION_GROUP_CREATED, actor=self.member
            ).exists()
        )

    def test_solo_room_cannot_create_group(self):
        solo = Room.objects.create(name='Solo', created_by=self.owner)
        solo.members.add(self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('create-room-group', args=[solo.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Chat.objects.filter(kind=Chat.KIND_GROUP).exists())

    def test_non_member_denied(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('create-room-group', args=[self.room.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Chat.objects.filter(kind=Chat.KIND_GROUP).exists())


class GroupCreationPolicyTests(TestCase):
    def setUp(self):
        self.admin = make_user('policyadmin')
        admin_profile = Profile.for_user(self.admin)
        admin_profile.role = Profile.ROLE_ADMIN
        admin_profile.save(update_fields=['role'])
        self.user = make_user('policyuser')
        self.other = make_user('policyother')

    def _toggle(self, enabled):
        app_settings = AppSettings.load()
        app_settings.allow_user_group_creation = enabled
        app_settings.save(update_fields=['allow_user_group_creation'])

    def test_admin_toggle_disables_user_group_creation(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin-panel'), {'action': 'toggle-group-creation'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AppSettings.load().allow_user_group_creation)
        self.assertTrue(
            AuditEvent.objects.filter(action=AuditEvent.ACTION_SETTINGS_CHANGED).exists()
        )

    def test_user_blocked_when_disabled(self):
        self.client.force_login(self.user)
        self._toggle(False)
        response = self.client.post(
            reverse('create-group-chat'),
            {'title': 'Blocked', 'members': [str(self.other.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Chat.objects.filter(kind=Chat.KIND_GROUP).exists())

    def test_admin_can_create_when_disabled_for_users(self):
        self.client.force_login(self.admin)
        self._toggle(False)
        response = self.client.post(
            reverse('create-group-chat'),
            {'title': 'Admin Group', 'members': [str(self.user.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Chat.objects.filter(title='Admin Group', kind=Chat.KIND_GROUP).exists())

    def test_room_group_blocked_when_disabled(self):
        room = Room.objects.create(name='Quiet', created_by=self.user)
        room.members.set([self.user, self.other])
        self.client.force_login(self.user)
        self._toggle(False)
        response = self.client.post(reverse('create-room-group', args=[room.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Chat.objects.filter(kind=Chat.KIND_GROUP).exists())

    def test_chats_page_hides_group_form_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('chats'))
        self.assertContains(response, 'group-create')
        self._toggle(False)
        response = self.client.get(reverse('chats'))
        self.assertNotContains(response, 'group-create')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('chats'))
        self.assertContains(response, 'group-create')

    def test_room_page_shows_group_button(self):
        room = Room.objects.create(name='Chatroom', created_by=self.user)
        room.members.set([self.user, self.other])
        self.client.force_login(self.user)
        response = self.client.get(reverse('room-detail', args=[room.pk]))
        self.assertContains(response, '/rooms/%d/group/new/' % room.pk)
        self._toggle(False)
        response = self.client.get(reverse('room-detail', args=[room.pk]))
        self.assertNotContains(response, '/rooms/%d/group/new/' % room.pk)

    def test_admin_panel_shows_settings_toggle(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin-panel'))
        self.assertContains(response, 'toggle-group-creation')
