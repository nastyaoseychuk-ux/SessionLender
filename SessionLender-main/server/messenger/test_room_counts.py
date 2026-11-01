from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Post, Room


class RoomCountTests(TestCase):
    def test_counts_include_every_member_not_just_the_viewer(self):
        viewer = User.objects.create_user('viewer')
        other = User.objects.create_user('other')
        third = User.objects.create_user('third')
        small = Room.objects.create(name='Small', created_by=viewer)
        small.members.add(viewer, other)
        large = Room.objects.create(name='Large', created_by=viewer)
        large.members.add(viewer, other, third)
        Post.objects.create(room=large, author=viewer, caption='One')
        Post.objects.create(room=large, author=other, caption='Two')
        private = Room.objects.create(name='Private', created_by=third)
        private.members.add(third)
        self.client.force_login(viewer)
        for route in ['rooms', 'home']:
            response = self.client.get(reverse(route))
            rooms = {room.pk: room for room in response.context['rooms']}
            self.assertEqual(rooms[small.pk].member_count, 2)
            self.assertEqual(rooms[large.pk].member_count, 3)
            self.assertEqual(rooms[large.pk].post_count, 2)
            self.assertNotIn(private.pk, rooms)
        response = self.client.get(reverse('user-profile', args=[other.profile.nickname]))
        rooms = {room.pk: room for room in response.context['shared_rooms']}
        self.assertEqual(rooms[large.pk].member_count, 3)
        self.assertEqual(rooms[small.pk].member_count, 2)
