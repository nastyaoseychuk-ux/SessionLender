from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape


class AboutPageTests(TestCase):
    def test_public_page_without_database_queries(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="demoChatForm"')
        self.assertContains(response, 'data-slide=', count=4)

    def test_authenticated_and_banned_access(self):
        user = User.objects.create_user('aboutreader')
        self.client.force_login(user)
        with self.assertNumQueries(0):
            self.assertEqual(self.client.get(reverse('about')).status_code, 200)
        user.profile.is_banned = True
        user.profile.save(update_fields=['is_banned'])
        self.assertEqual(self.client.get(reverse('about')).status_code, 200)

    def test_download_and_github_links(self):
        with patch.dict('os.environ', {'PROJECT_GITHUB_URL': 'https://github.com/nastyaoseychuk-ux'}):
            response = self.client.get(reverse('about'))
        for value in [escape(settings.ANDROID_DOWNLOAD_URL), escape(settings.DESKTOP_DOWNLOAD_URL), 'https://github.com/nastyaoseychuk-ux']:
            self.assertContains(response, value)

    def test_auth_pages_have_link(self):
        for name in ['login', 'register']:
            self.assertContains(self.client.get(reverse(name)), 'href="/about/"')

    def test_sidebar_link_above_account(self):
        self.client.force_login(User.objects.create_user('sidebarreader'))
        html = self.client.get(reverse('home')).content.decode()
        self.assertLess(html.index('about-project-link'), html.index('sidebar-account'))

    def test_gallery_assets_exist(self):
        for theme in ['dark', 'light']:
            for n in range(1, 5):
                self.assertTrue((settings.BASE_DIR / 'static' / 'about' / f'{theme}-{n}.webp').is_file())
