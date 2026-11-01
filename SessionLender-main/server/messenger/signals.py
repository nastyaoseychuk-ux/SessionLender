from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Chat, ChatMembership, ChatMessage, Profile


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    if created:
        Profile.objects.create(
            user=instance,
            nickname=instance.username,
            role=Profile.ROLE_ADMIN if instance.is_staff or instance.is_superuser else Profile.ROLE_USER,
        )
        return

    profile, _ = Profile.objects.get_or_create(
        user=instance,
        defaults={'nickname': instance.username},
    )
    if (instance.is_staff or instance.is_superuser) and profile.role != Profile.ROLE_ADMIN:
        profile.role = Profile.ROLE_ADMIN
        profile.save(update_fields=['role'])


@receiver(post_save, sender=ChatMessage)
def touch_chat(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return
    if not created:
        return
    Chat.objects.filter(pk=instance.chat_id).update(updated_at=timezone.now())
    ChatMembership.objects.filter(chat_id=instance.chat_id, user_id=instance.author_id).update(
        last_read_at=instance.created_at
    )


@receiver(post_delete, sender=ChatMembership)
def cleanup_empty_chat(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    chat_id = instance.chat_id
    transaction.on_commit(
        lambda: Chat.objects.filter(pk=chat_id, memberships__isnull=True).delete()
    )


@receiver(post_save, sender=ChatMessage)
def broadcast_message(sender, instance, created, **kwargs):
    if kwargs.get('raw') or not created:
        return
    from .delivery import relay

    chat_id, message_id = instance.chat_id, instance.pk
    recipients = list(
        ChatMembership.objects.filter(chat_id=chat_id).values_list('user_id', flat=True)
    )
    events = [(f'chat_{chat_id}', {'type': 'chat.message', 'id': message_id})]
    for user_id in recipients:
        events.append((f'user_{user_id}', {'type': 'inbox.changed'}))
        if user_id != instance.author_id:
            events.append(
                (
                    f'user_{user_id}',
                    {'type': 'server.notice', 'kind': 'message', 'id': message_id},
                )
            )
    transaction.on_commit(lambda: relay(events), robust=True)
