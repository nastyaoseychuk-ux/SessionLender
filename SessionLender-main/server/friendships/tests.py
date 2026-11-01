from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from messenger.models import Notification
from .models import Friendship


class FriendsTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice')
        self.bob = User.objects.create_user('bob')
        self.stranger = User.objects.create_user('stranger')
        self.client.force_login(self.alice)

    def act(self, target, action):
        return self.client.post(reverse('friend-update', args=[target.pk]), {'friend_action': action})

    def request_friend(self):
        self.act(self.bob, 'add')
        return Friendship.objects.get(owner=self.alice, friend=self.bob)

    def test_request_follow_status_and_notification(self):
        link = self.request_friend()
        self.act(self.bob, 'add')
        self.assertEqual(Friendship.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(link.status, Friendship.PENDING)
        response = self.client.get(reverse('friends'))
        self.assertEqual(list(response.context['profiles']), [self.bob.profile])
        self.assertContains(response, 'Стежу')
        self.client.force_login(self.bob)
        self.assertEqual(list(self.client.get(reverse('friends')).context['profiles']), [])
        response = self.client.get(reverse('friends'), {'filter': 'requests'})
        self.assertEqual(list(response.context['profiles']), [self.alice.profile])
        self.assertContains(response, 'Стежать')
        self.assertContains(response, 'Прийняти')
        response = self.client.get(reverse('notifications'))
        self.assertContains(response, 'Користувач @alice хоче з вами дружити')
        self.assertContains(response, 'Відхилити')

    def test_accept_creates_mutual_friendship_and_clears_request(self):
        link = self.request_friend()
        self.client.force_login(self.bob)
        self.act(self.alice, 'accept')
        self.assertEqual(Friendship.objects.filter(status=Friendship.ACCEPTED).count(), 2)
        self.assertEqual(list(self.client.get(reverse('friends')).context['profiles']), [self.alice.profile])
        self.assertFalse(self.client.get(reverse('friends'), {'filter': 'requests'}).context['profiles'])
        self.assertContains(self.client.get(reverse('notifications')), 'В друзях')
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(reverse('friends')), 'В друзях ✓')
        link.refresh_from_db()
        self.assertTrue(link.notification.is_read)

    def test_decline_keeps_following_without_friendship_or_pending_request(self):
        link = self.request_friend()
        self.client.force_login(self.bob)
        self.act(self.alice, 'reject')
        link.refresh_from_db()
        self.assertEqual(link.status, Friendship.REJECTED)
        self.assertFalse(Friendship.objects.filter(owner=self.bob).exists())
        self.assertFalse(self.client.get(reverse('friends'), {'filter': 'requests'}).context['profiles'])
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(reverse('friends')), 'Стежу')

    def test_unrelated_user_and_sender_cannot_accept(self):
        link = self.request_friend()
        self.assertEqual(self.act(self.bob, 'accept').status_code, 404)
        self.client.force_login(self.stranger)
        self.assertEqual(self.act(self.alice, 'accept').status_code, 404)
        link.refresh_from_db()
        self.assertEqual(link.status, Friendship.PENDING)

    def test_cross_requests_need_explicit_acceptance(self):
        self.request_friend()
        self.client.force_login(self.bob)
        self.act(self.alice, 'add')
        self.assertEqual(Friendship.objects.filter(status=Friendship.PENDING).count(), 2)
        self.act(self.alice, 'accept')
        self.assertEqual(Friendship.objects.filter(status=Friendship.ACCEPTED).count(), 2)
        self.assertFalse(Notification.objects.filter(is_read=False).exists())

    def test_cancel_and_remove_mutual_friendship(self):
        self.request_friend()
        self.act(self.bob, 'remove')
        self.assertFalse(Friendship.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.request_friend()
        self.client.force_login(self.bob)
        self.act(self.alice, 'accept')
        self.act(self.alice, 'remove')
        self.assertFalse(Friendship.objects.exists())

    def test_auth_csrf_self_and_banned(self):
        self.assertEqual(self.act(self.alice, 'add').status_code, 400)
        self.assertEqual(self.client.get(reverse('friend-update', args=[self.bob.pk])).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(client.post(reverse('friend-update', args=[self.bob.pk]), {'friend_action':'add'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.act(self.bob, 'add').status_code, 302)
        self.client.force_login(self.alice)
        profile = self.bob.profile
        profile.is_banned = True
        profile.save()
        self.assertEqual(self.act(self.bob, 'add').status_code, 404)

    def test_search_filters_only_my_list_or_my_requests(self):
        self.request_friend()
        response = self.client.get(reverse('friends'), {'q':'stranger'})
        self.assertFalse(response.context['profiles'])
        self.client.force_login(self.bob)
        self.assertFalse(self.client.get(reverse('friends'), {'filter':'requests', 'q':'stranger'}).context['profiles'])
