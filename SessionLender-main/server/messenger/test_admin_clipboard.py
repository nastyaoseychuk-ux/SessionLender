from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from .models import Profile, TemporaryCode


class AdminCodeClipboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('clipboard_admin')
        profile = self.admin.profile
        profile.role = Profile.ROLE_ADMIN
        profile.save(update_fields=['role'])
        self.target = User.objects.create_user('clipboard_target')
        self.data = {'profile_id': self.target.profile.pk, 'action': 'create-code'}
        self.client.force_login(self.admin)

    def test_json_returns_the_issued_code_without_caching(self):
        response = self.client.post(reverse('admin-panel'), self.data, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        code = TemporaryCode.objects.get(user=self.target, used=False).code
        self.assertEqual(response.json()['code'], code)
        self.assertIn(code, response.json()['message'])
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_normal_submission_still_displays_the_notice(self):
        response = self.client.post(reverse('admin-panel'), self.data, follow=True)
        code = TemporaryCode.objects.get(user=self.target, used=False).code
        self.assertContains(response, code)

    def test_regular_user_cannot_generate_codes_via_json(self):
        self.client.force_login(self.target)
        response = self.client.post(reverse('admin-panel'), self.data, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TemporaryCode.objects.exists())

    def test_json_submission_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('admin-panel'), self.data, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TemporaryCode.objects.exists())
