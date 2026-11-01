from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Friendship(models.Model):
    """An outgoing follow/request; accepted friendships have a row in both directions."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friendships')
    friend = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='added_by_friends')
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    status = models.CharField(max_length=10, choices=[(PENDING, 'Очікує'), (ACCEPTED, 'В друзях'), (REJECTED, 'Відхилено')], default=PENDING)
    notification = models.OneToOneField('messenger.Notification', on_delete=models.SET_NULL, null=True, blank=True, related_name='friend_request')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'friend'], name='unique_personal_friend'),
            models.CheckConstraint(condition=~Q(owner=F('friend')), name='friend_is_not_self'),
        ]
