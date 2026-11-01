"""Private live events; payloads are resolved and authorized at delivery time."""

from django.db import transaction
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from .models import Post, Comment, PostLike, Room


def publish(kind, object_id, recipients):
    from .delivery import relay

    events = [
        (f"user_{user_id}", {"type": "server.notice", "kind": kind, "id": object_id})
        for user_id in set(recipients)
    ]
    transaction.on_commit(lambda: relay(events), robust=True)


@receiver(post_save, sender=Post)
def new_post(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        publish(
            "post",
            instance.pk,
            instance.room.members.exclude(pk=instance.author_id).values_list(
                "pk", flat=True
            ),
        )


@receiver(post_save, sender=Comment)
def new_comment(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created and instance.post.author_id != instance.author_id:
        publish("comment", instance.pk, [instance.post.author_id])


@receiver(post_save, sender=PostLike)
def new_like(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created and instance.post.author_id != instance.user_id:
        publish("like", instance.pk, [instance.post.author_id])


@receiver(m2m_changed, sender=Room.members.through)
def room_added(sender, instance, action, reverse, pk_set, **kwargs):
    if kwargs.get("raw"):
        return
    if action == "post_add":
        if reverse:
            for room_id in pk_set:
                publish("room", room_id, [instance.pk])
        else:
            publish("room", instance.pk, pk_set)
