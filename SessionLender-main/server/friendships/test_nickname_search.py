from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

class NicknameSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('searcher')
        self.target = User.objects.create_user('nickname')
        self.client.force_login(self.user)

    def test_missing_at_is_rejected(self):
        response = self.client.get(reverse('friends'), {'filter':'find','q':'nickname'})
        self.assertContains(response, 'Нікнейм має починатися із символу @')
        self.assertEqual(list(response.context['profiles']), [])

    def test_prefixed_query_finds_user_and_keeps_at_in_input(self):
        response = self.client.get(reverse('friends'), {'filter':'find','q':'@nickname'})
        self.assertEqual([p.user_id for p in response.context['profiles']], [self.target.pk])
        self.assertEqual(response.context['query'], '@nickname')
        self.assertEqual(response.context['query_error'], '')

    def test_empty_initial_page_has_no_warning(self):
        response = self.client.get(reverse('friends'), {'filter':'find'})
        self.assertEqual(response.context['query_error'], '')
        self.assertEqual(list(response.context['profiles']), [])

    def test_invalid_handle_has_warning_and_no_results(self):
        for query in ['@','@@nickname','@nick name','']:
            response = self.client.get(reverse('friends'), {'filter':'find','q':query})
            self.assertTrue(response.context['query_error'])
            self.assertEqual(list(response.context['profiles']), [])
