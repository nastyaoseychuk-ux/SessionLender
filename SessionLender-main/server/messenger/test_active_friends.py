from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from friendships.models import Friendship


class ActiveFriendsTests(TestCase):
    def test_admin_sees_all_others_only_accepted_friends(self):
        friend = User.objects.create_user('friend')
        following = User.objects.create_user('following')
        stranger = User.objects.create_user('stranger')
        for person in [friend, following, stranger]:
            profile = person.profile
            profile.last_seen = timezone.now()
            profile.save()
        for role in ['admin', 'user', 'analyst']:
            viewer = User.objects.create_user('viewer_' + role)
            profile = viewer.profile
            profile.role = role
            profile.save()
            Friendship.objects.create(owner=viewer, friend=friend, status='accepted')
            Friendship.objects.create(owner=viewer, friend=following, status='pending')
            self.client.force_login(viewer)
            response = self.client.get(reverse('home'))
            active_ids = {profile.user_id for profile in response.context['active_people']}
            self.assertIn(friend.pk, active_ids)
            if role == 'admin':
                self.assertIn(stranger.pk, active_ids)
                self.assertIn(following.pk, active_ids)
            else:
                self.assertEqual(active_ids, {friend.pk})
                self.assertNotContains(response, 'href="/people/">Усі')
