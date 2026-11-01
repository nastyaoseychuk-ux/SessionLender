from django.contrib.auth.models import User
from django.test import TestCase, override_settings


@override_settings(
    ANDROID_DOWNLOAD_URL="https://downloads.example/app.apk",
    DESKTOP_DOWNLOAD_URL="https://downloads.example/app.exe",
)
class DownloadButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("downloadtester")

    def setUp(self):
        self.client.force_login(self.user)

    def test_desktop_browser_gets_desktop_link(self):
        response = self.client.get(
            "/", HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )
        self.assertContains(response, 'href="https://downloads.example/app.exe"')
        self.assertNotContains(response, 'href="https://downloads.example/app.apk"')

    def test_mobile_browser_gets_apk(self):
        for agent in [
            "Mozilla/5.0 (Linux; Android 13) Chrome/156 Mobile",
            "Mozilla/5.0 (iPhone) Safari/605",
        ]:
            with self.subTest(agent=agent):
                response = self.client.get("/", HTTP_USER_AGENT=agent)
                self.assertContains(
                    response, 'href="https://downloads.example/app.apk"'
                )
                self.assertNotContains(
                    response, 'href="https://downloads.example/app.exe"'
                )

    def test_mobile_client_hint_gets_apk(self):
        response = self.client.get(
            "/", HTTP_USER_AGENT="Reduced browser UA", HTTP_SEC_CH_UA_MOBILE="?1"
        )
        self.assertContains(response, 'href="https://downloads.example/app.apk"')

    def test_app_and_legacy_webview_hide_download_button(self):
        for agent in [
            "Mozilla/5.0 SessionLenderAndroid/0.3.4",
            "Mozilla/5.0 (Linux; Android 13; Phone Build/X; wv) Chrome/156",
        ]:
            with self.subTest(agent=agent):
                response = self.client.get("/", HTTP_USER_AGENT=agent)
                self.assertNotContains(response, "topbar-download")
