from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import Friendship


class FindFriendsTests(TestCase):
    def test_all_roles_can_search_without_opening_people(self):
        target = User.objects.create_user('new_person')
        banned = User.objects.create_user('new_banned')
        profile = banned.profile
        profile.is_banned = True
        profile.save()
        for role in ['user', 'analyst', 'admin']:
            viewer = User.objects.create_user('viewer_' + role)
            profile = viewer.profile
            profile.role = role
            profile.save()
            Friendship.objects.create(owner=viewer, friend=target)
            self.client.force_login(viewer)
            response = self.client.get(reverse('friends'), {'filter': 'find'})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['profiles'])
            self.assertContains(response, '/friends/?filter=find')
            self.assertNotContains(response, 'href="/people/">Знайти друзів')
            response = self.client.get(reverse('friends'), {'filter': 'find', 'q': '@new_'})
            self.assertEqual(list(response.context['profiles']), [target.profile])
            self.assertContains(response, 'name="filter" value="find"')
            self.assertTrue(Friendship.objects.filter(owner=viewer, friend=target).exists())
            if role != 'admin':
                self.assertEqual(self.client.get(reverse('people')).status_code, 403)


class PeopleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('plain_person')
        self.admin = User.objects.create_user('directory_admin')
        self.admin.profile.role = 'admin'
        self.admin.profile.save(update_fields=['role'])

    def test_plain_user_gets_403_on_people_directory(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('people')).status_code, 403)

    def test_admin_sees_people_directory(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('people')).status_code, 200)

    def test_start_chat_error_does_not_bounce_into_403(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('start-chat', args=[self.user.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse('people'))


@override_settings(TEST=False)
class FriendSearchThrottleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user('throttleme')
        self.client.force_login(self.user)

    def test_find_search_is_rate_limited(self):
        blocked = 'Забагато спроб пошуку'
        for i in range(20):
            response = self.client.get(reverse('friends'), {'filter': 'find', 'q': '@nick'})
            self.assertNotContains(response, blocked)
        response = self.client.get(reverse('friends'), {'filter': 'find', 'q': '@nick'})
        self.assertContains(response, blocked)

    def test_invalid_queries_not_counted_toward_limit(self):
        blocked = 'Забагато спроб пошуку'
        for i in range(25):
            self.client.get(reverse('friends'), {'filter': 'find', 'q': 'no-at-sign'})
        response = self.client.get(reverse('friends'), {'filter': 'find', 'q': '@nick'})
        self.assertNotContains(response, blocked)
