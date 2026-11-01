from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from friendships.models import Friendship

from .models import (
    Chat,
    ChatMembership,
    ChatMessage,
    Comment,
    Post,
    PostLike,
    Profile,
    Room,
    RoomInvitation,
    TemporaryCode,
)

PASSWORD = 'StrongPass123!'


def make_user(username, password=PASSWORD, **profile_fields):
    user = User.objects.create_user(username=username, password=password)
    profile = user.profile
    for field, value in profile_fields.items():
        setattr(profile, field, value)
    profile.save()
    return user


class AuthTests(TestCase):
    def test_register_creates_profile_and_logs_in(self):
        response = self.client.post(
            reverse('register'),
            {'nickname': 'alice', 'password1': PASSWORD, 'password2': PASSWORD},
        )
        self.assertRedirects(response, reverse('home'))
        user = User.objects.get(username='alice')
        self.assertEqual(user.profile.nickname, 'alice')
        self.assertEqual(user.profile.role, Profile.ROLE_USER)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_register_rejects_duplicate_nickname_case_insensitively(self):
        make_user('Alice')
        response = self.client.post(
            reverse('register'),
            {'nickname': 'alice', 'password1': PASSWORD, 'password2': PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже зайнятий')
        self.assertEqual(User.objects.count(), 1)

    def test_login_with_nickname(self):
        make_user('alice')
        response = self.client.post(
            reverse('login'),
            {'nickname': 'ALICE', 'password': PASSWORD},
        )
        self.assertRedirects(response, reverse('home'))

    def test_banned_user_cannot_login(self):
        user = make_user('alice')
        user.profile.is_banned = True
        user.profile.save()
        response = self.client.post(
            reverse('login'),
            {'nickname': 'alice', 'password': PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'заблоковано')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_banned_user_is_logged_out_on_next_request(self):
        user = make_user('alice')
        self.client.force_login(user)
        user.profile.is_banned = True
        user.profile.save()
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_temporary_code_login_marks_code_used(self):
        user = make_user('alice')
        code = TemporaryCode.generate_for(user)
        response = self.client.post(reverse('login'), {'code': code.code})
        self.assertRedirects(response, reverse('profile'))
        code.refresh_from_db()
        self.assertTrue(code.used)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_expired_temporary_code_is_rejected(self):
        user = make_user('alice')
        code = TemporaryCode.generate_for(user)
        code.expires_at = timezone.now() - timedelta(minutes=1)
        code.save(update_fields=['expires_at'])
        response = self.client.post(reverse('login'), {'code': code.code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'недійсний')


class RoomAndPostTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.room = Room.objects.create(name='Team', description='Work room', created_by=self.alice)
        self.room.members.add(self.alice)
        # Політика запросів: лише друзі (див. invitations.may_invite_user).
        Friendship.objects.create(owner=self.alice, friend=self.bob, status=Friendship.ACCEPTED)
        Friendship.objects.create(owner=self.bob, friend=self.alice, status=Friendship.ACCEPTED)

    def test_create_room_adds_owner_as_member(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('create-room'),
            {'name': 'New room', 'description': 'Description'},
        )
        room = Room.objects.get(name='New room')
        self.assertRedirects(response, reverse('room-detail', args=[room.pk]))
        self.assertEqual(room.created_by, self.alice)
        self.assertTrue(room.members.filter(pk=self.alice.pk).exists())

    def test_member_can_view_room_and_non_member_cannot(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('room-detail', args=[self.room.pk])).status_code, 200)

        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse('room-detail', args=[self.room.pk])).status_code, 403)

    def test_owner_can_add_member(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('add-member', args=[self.room.pk]),
            {'nickname': 'bob'},
        )
        self.assertRedirects(response, reverse('room-detail', args=[self.room.pk]))
        self.assertFalse(self.room.members.filter(pk=self.bob.pk).exists())
        self.assertTrue(RoomInvitation.objects.filter(
            room=self.room, user=self.bob, status=RoomInvitation.PENDING,
        ).exists())

    def test_non_owner_cannot_add_member(self):
        self.room.members.add(self.bob)
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse('add-member', args=[self.room.pk]),
            {'nickname': 'alice'},
        )
        self.assertEqual(response.status_code, 404)

    def test_create_post_and_comment(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('create-post'),
            {'room': self.room.pk, 'caption': 'Hello'},
        )
        post = Post.objects.get(caption='Hello')
        self.assertRedirects(response, reverse('room-detail', args=[self.room.pk]))
        self.assertEqual(post.author, self.alice)

        response = self.client.post(
            reverse('add-comment', args=[post.pk]),
            {'text': 'First comment'},
            HTTP_REFERER=reverse('room-detail', args=[self.room.pk]),
        )
        self.assertRedirects(response, reverse('room-detail', args=[self.room.pk]))
        self.assertTrue(Comment.objects.filter(post=post, author=self.alice, text='First comment').exists())

    def test_non_member_cannot_comment(self):
        post = Post.objects.create(author=self.alice, room=self.room, caption='Hello')
        self.client.force_login(self.bob)
        response = self.client.post(reverse('add-comment', args=[post.pk]), {'text': 'Nope'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_author_can_delete_post(self):
        post = Post.objects.create(author=self.alice, room=self.room, caption='Hello')
        self.client.force_login(self.alice)
        response = self.client.post(reverse('delete-post', args=[post.pk]))
        self.assertRedirects(response, reverse('room-detail', args=[self.room.pk]))
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_owner_cannot_leave_but_member_can(self):
        self.room.members.add(self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(reverse('leave-room', args=[self.room.pk]), follow=True)
        self.assertContains(response, 'Власник не може залишити кімнату')
        self.assertTrue(self.room.members.filter(pk=self.alice.pk).exists())

        self.client.force_login(self.bob)
        response = self.client.post(reverse('leave-room', args=[self.room.pk]))
        self.assertRedirects(response, reverse('rooms'))
        self.assertFalse(self.room.members.filter(pk=self.bob.pk).exists())

    def test_owner_can_remove_member_but_not_self(self):
        self.room.members.add(self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(reverse('remove-member', args=[self.room.pk, self.bob.pk]))
        self.assertRedirects(response, reverse('room-detail', args=[self.room.pk]))
        self.assertFalse(self.room.members.filter(pk=self.bob.pk).exists())

        response = self.client.post(reverse('remove-member', args=[self.room.pk, self.alice.pk]), follow=True)
        self.assertContains(response, 'Не можна вилучити власника')
        self.assertTrue(self.room.members.filter(pk=self.alice.pk).exists())

    def test_owner_can_delete_room(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse('delete-room', args=[self.room.pk]))
        self.assertRedirects(response, reverse('rooms'))
        self.assertFalse(Room.objects.filter(pk=self.room.pk).exists())


class AdminTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin', role=Profile.ROLE_ADMIN)
        self.admin.is_staff = True
        self.admin.save()
        self.user = make_user('bob')

    def test_regular_user_cannot_open_admin_panel(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('admin-panel')).status_code, 403)

    def test_admin_can_open_admin_panel(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin-panel'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '@bob')

    def test_admin_can_ban_and_unban_user(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.user.profile.pk, 'action': 'toggle-ban'},
        )
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.is_banned)

        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.user.profile.pk, 'action': 'toggle-ban'},
        )
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.is_banned)

    def test_admin_cannot_ban_self(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.admin.profile.pk, 'action': 'toggle-ban'},
        )
        self.admin.profile.refresh_from_db()
        self.assertFalse(self.admin.profile.is_banned)

    def test_admin_can_change_role(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.user.profile.pk, 'action': 'set-role', 'role': Profile.ROLE_ANALYST},
        )
        self.user.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.role, Profile.ROLE_ANALYST)
        self.assertFalse(self.user.is_staff)

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('analyst')).status_code, 200)

    def test_admin_can_create_code_and_reset_password(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.user.profile.pk, 'action': 'create-code'},
        )
        self.assertEqual(TemporaryCode.objects.filter(user=self.user, used=False).count(), 1)

        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.user.profile.pk, 'action': 'reset-password'},
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(PASSWORD))

    def test_admin_cannot_reset_own_password_from_panel(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': self.admin.profile.pk, 'action': 'reset-password'},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(PASSWORD))

    def test_non_superuser_cannot_reset_superuser_password(self):
        superuser = make_user('root')
        superuser.is_staff = True
        superuser.is_superuser = True
        superuser.save()
        self.client.force_login(self.admin)
        self.client.post(
            reverse('admin-panel'),
            {'profile_id': superuser.profile.pk, 'action': 'reset-password'},
        )
        superuser.refresh_from_db()
        self.assertTrue(superuser.check_password(PASSWORD))


class AnalystTests(TestCase):
    def setUp(self):
        self.analyst = make_user('analyst', role=Profile.ROLE_ANALYST)

    def test_analyst_panel_renders(self):
        self.client.force_login(self.analyst)
        response = self.client.get(reverse('analyst'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Аналітика активності')

    def test_regular_user_cannot_open_analyst_panel(self):
        user = make_user('bob')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('analyst')).status_code, 403)

    def test_analyst_can_export_csv(self):
        self.client.force_login(self.analyst)
        response = self.client.get(reverse('analyst-export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="sessionlender-report.csv"', response['Content-Disposition'])
        content = response.content.decode('utf-8-sig')
        self.assertIn('Користувачів', content)
        self.assertIn('Дописи', content)

    def test_regular_user_cannot_export_csv(self):
        user = make_user('bob')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('analyst-export')).status_code, 403)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')

    def test_change_nickname(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('profile'),
            {'form': 'nickname', 'nickname': 'alice-new'},
            follow=True,
        )
        self.assertContains(response, 'Нікнейм оновлено')
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.username, 'alice-new')
        self.assertEqual(self.user.profile.nickname, 'alice-new')

    def test_change_password(self):
        self.client.force_login(self.user)
        new_password = 'AnotherPass456!'
        response = self.client.post(
            reverse('profile'),
            {
                'form': 'password',
                'old_password': PASSWORD,
                'new_password1': new_password,
                'new_password2': new_password,
            },
            follow=True,
        )
        self.assertContains(response, 'Пароль змінено')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_nickname_must_be_unique(self):
        make_user('bob')
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('profile'),
            {'form': 'nickname', 'nickname': 'bob'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже зайнятий')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'alice')

    def test_update_profile_bio(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('profile'),
            {'form': 'settings', 'bio': 'Привіт, я тестовий користувач.'},
            follow=True,
        )
        self.assertContains(response, 'Профіль оновлено')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.bio, 'Привіт, я тестовий користувач.')


class LikeAndChatTests(TestCase):
    def setUp(self):
        self.alice = make_user('alice')
        self.bob = make_user('bob')
        self.carol = make_user('carol')
        self.room = Room.objects.create(name='Room', created_by=self.alice)
        self.room.members.add(self.alice, self.bob)
        self.post = Post.objects.create(author=self.alice, room=self.room, caption='Hello')

    def test_toggle_like_creates_and_removes_like(self):
        self.client.force_login(self.bob)
        self.client.post(reverse('toggle-like', args=[self.post.pk]))
        self.assertEqual(PostLike.objects.filter(post=self.post, user=self.bob).count(), 1)

        self.client.post(reverse('toggle-like', args=[self.post.pk]))
        self.assertEqual(PostLike.objects.filter(post=self.post, user=self.bob).count(), 0)

    def test_non_member_cannot_like_post(self):
        self.client.force_login(self.carol)
        response = self.client.post(reverse('toggle-like', args=[self.post.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PostLike.objects.filter(post=self.post).exists())

    def test_chat_between_is_unique(self):
        chat, created = Chat.between(self.alice, self.bob)
        self.assertTrue(created)
        same_chat, created_again = Chat.between(self.bob, self.alice)
        self.assertFalse(created_again)
        self.assertEqual(chat.pk, same_chat.pk)
        self.assertEqual(chat.memberships.count(), 2)

    def test_start_chat_creates_chat_and_redirects(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse('start-chat', args=[self.bob.pk]))
        chat = Chat.objects.get()
        self.assertRedirects(response, reverse('chat-detail', args=[chat.pk]))
        self.assertTrue(ChatMembership.objects.filter(chat=chat, user=self.alice).exists())
        self.assertTrue(ChatMembership.objects.filter(chat=chat, user=self.bob).exists())

    def test_chat_message_creates_unread_for_other_member(self):
        chat, _ = Chat.between(self.alice, self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse('chat-detail', args=[chat.pk]),
            {'text': 'Привіт!'},
        )
        self.assertRedirects(response, reverse('chat-detail', args=[chat.pk]))
        self.assertEqual(ChatMessage.objects.filter(chat=chat).count(), 1)
        self.assertEqual(ChatMembership.unread_total_for(self.bob), 1)
        self.assertEqual(ChatMembership.unread_total_for(self.alice), 0)

    def test_chat_poll_returns_messages_and_marks_read(self):
        chat, _ = Chat.between(self.alice, self.bob)
        first = ChatMessage.objects.create(chat=chat, author=self.alice, text='Перше')
        self.client.force_login(self.bob)
        response = self.client.get(reverse('chat-poll', args=[chat.pk]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['messages']), 1)
        self.assertEqual(payload['messages'][0]['text'], 'Перше')
        self.assertEqual(ChatMembership.unread_total_for(self.bob), 0)

        ChatMessage.objects.create(chat=chat, author=self.alice, text='Друге')
        response = self.client.get(
            reverse('chat-poll', args=[chat.pk]),
            {'after': first.created_at.isoformat()},
        )
        payload = response.json()
        self.assertEqual(len(payload['messages']), 1)
        self.assertEqual(payload['messages'][0]['text'], 'Друге')

    def test_non_member_cannot_open_chat(self):
        chat, _ = Chat.between(self.alice, self.bob)
        self.client.force_login(self.carol)
        self.assertEqual(self.client.get(reverse('chat-detail', args=[chat.pk])).status_code, 404)

    def test_chat_pages_render(self):
        chat, _ = Chat.between(self.alice, self.bob)
        ChatMessage.objects.create(chat=chat, author=self.alice, text='Привіт')
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('chats')).status_code, 200)
        self.assertEqual(self.client.get(reverse('chat-detail', args=[chat.pk])).status_code, 200)


class PageSmokeTests(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.room = Room.objects.create(name='Room', created_by=self.user)
        self.room.members.add(self.user)
        Post.objects.create(author=self.user, room=self.room, caption='Post')

    def test_authenticated_pages_render(self):
        self.client.force_login(self.user)
        for url in (
            reverse('home'),
            reverse('rooms'),
            reverse('room-detail', args=[self.room.pk]),
            reverse('friends'),
            reverse('profile'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_people_catalog_requires_admin(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('people')).status_code, 403)

    def test_auth_pages_render(self):
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, f'{reverse("login")}?next={reverse("home")}')
