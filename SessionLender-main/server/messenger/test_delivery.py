import uuid
from unittest.mock import patch, PropertyMock
from django.test import TransactionTestCase, Client
from django.contrib.auth.models import User
from django.db.models.fields.files import FieldFile
from .models import Chat, ChatMessage
from .sending import store_message


class ReliableDeliveryTests(TransactionTestCase):
    def setUp(self):
        self.a=User.objects.create_user('deliveryalice',password='test-password')
        self.b=User.objects.create_user('deliverybob',password='test-password')
        self.other=User.objects.create_user('deliveryoutsider',password='test-password')
        self.chat,_=Chat.between(self.a,self.b)
        self.client.force_login(self.a)
        self.url=f'/messages/{self.chat.pk}/send/'
        self.packet={'text':'Перше повідомлення', 'client_nonce':str(uuid.uuid4())}

    def test_same_attempt_retried_after_lost_ack_is_not_duplicated(self):
        first=self.client.post(self.url,self.packet,content_type='application/json')
        second=self.client.post(self.url,self.packet,content_type='application/json')
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(ChatMessage.objects.count(),1)
        self.assertEqual(first.json()['message']['text'],self.packet['text'])

    def test_nonce_cannot_silently_change_saved_text(self):
        self.client.post(self.url,self.packet,content_type='application/json')
        self.packet['text']='Інший текст'
        self.assertEqual(self.client.post(self.url,self.packet,content_type='application/json').status_code,409)
        self.assertEqual(ChatMessage.objects.count(),1)

    def test_relay_outage_does_not_turn_committed_send_into_failure(self):
        with patch('messenger.delivery.get_channel_layer',side_effect=ConnectionError('Simulated broker outage')):
            with self.assertLogs('messenger.delivery',level='ERROR'):
                reply=self.client.post(self.url,self.packet,content_type='application/json')
        self.assertEqual(reply.status_code,200)
        retry=self.client.post(self.url,self.packet,content_type='application/json')
        self.assertEqual(retry.json()['id'],reply.json()['id'])
        self.assertEqual(ChatMessage.objects.count(),1)

    def test_http_and_websocket_use_same_idempotency_key(self):
        ws=store_message(self.a,self.chat.pk,self.packet['text'],self.packet['client_nonce'])
        http=self.client.post(self.url,self.packet,content_type='application/json')
        self.assertEqual(ws['id'],http.json()['id'])
        self.assertEqual(ChatMessage.objects.count(),1)

    def test_access_and_nonce_validation(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url,self.packet,content_type='application/json').status_code,403)
        self.client.force_login(self.a)
        self.packet['client_nonce']='invalid'
        self.assertEqual(self.client.post(self.url,self.packet,content_type='application/json').status_code,400)
        self.assertFalse(ChatMessage.objects.exists())

    def test_http_fallback_requires_csrf(self):
        browser=Client(enforce_csrf_checks=True);browser.force_login(self.a)
        self.assertEqual(browser.post(self.url,self.packet,content_type='application/json').status_code,403)
        self.assertFalse(ChatMessage.objects.exists())

    def test_send_ack_never_fetches_cloud_avatar(self):
        profile=self.a.profile;profile.avatar.name='avatars/test.png';profile.save(update_fields=['avatar'])
        with patch.object(FieldFile,'url',new_callable=PropertyMock,side_effect=RuntimeError('Cloud image store unavailable')):
            reply=self.client.post(self.url,self.packet,content_type='application/json')
        self.assertEqual(reply.status_code,200)
        self.assertEqual(reply.json()['message']['avatar'],f'/people/{self.a.pk}/avatar/')
