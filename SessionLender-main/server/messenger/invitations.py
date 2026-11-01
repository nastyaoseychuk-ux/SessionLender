"""Room access is granted only after the invited user accepts."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Notification, Profile, Room, RoomInvitation
from .notifications import publish


def may_invite_user(inviter, user):
    if Profile.for_user(inviter).role == Profile.ROLE_ADMIN:
        return True
    from friendships.models import Friendship
    return Friendship.objects.filter(
        owner=inviter, friend=user, status=Friendship.ACCEPTED,
    ).exists()


@transaction.atomic
def invite_to_room(room, inviter, user):
    # Serialize invitations for this room to prevent duplicate notifications.
    room = Room.objects.select_for_update().get(pk=room.pk)
    if room.created_by_id != inviter.pk:
        raise PermissionDenied
    if not user.is_active or Profile.objects.filter(user=user, is_banned=True).exists():
        raise PermissionDenied
    if not may_invite_user(inviter, user):
        raise PermissionDenied('Запрошувати до кімнати можна лише друзів.')
    if room.members.filter(pk=user.pk).exists():
        return None
    invitation, created = RoomInvitation.objects.get_or_create(
        room=room, user=user, defaults={'inviter': inviter},
    )
    if not created and invitation.status == RoomInvitation.PENDING:
        return invitation
    invitation.inviter = inviter
    invitation.status = RoomInvitation.PENDING
    invitation.created_at = timezone.now()
    invitation.responded_at = None
    invitation.save()
    text = f'Вас запросив @{inviter.username} до кімнати {room.name}'
    Notification.objects.update_or_create(
        invitation=invitation,
        defaults={'user': user, 'actor': inviter, 'kind': Notification.KIND_SYSTEM,
                  'text': text[:255], 'is_read': False, 'created_at': timezone.now()},
    )
    publish('room_invitation', invitation.pk, [user.pk])
    return invitation


@transaction.atomic
def respond_to_invitation(invitation_id, user, action):
    invitation = get_object_or_404(
        RoomInvitation.objects.select_for_update(), pk=invitation_id, user=user,
    )
    if invitation.status != RoomInvitation.PENDING:
        return invitation
    if not user.is_active or Profile.objects.filter(user=user, is_banned=True).exists():
        raise PermissionDenied
    if action == 'accept':
        invitation.room.members.add(user)
        invitation.status = RoomInvitation.ACCEPTED
    elif action == 'reject':
        invitation.status = RoomInvitation.REJECTED
    else:
        raise ValueError('Unknown invitation action')
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=['status', 'responded_at'])
    Notification.objects.filter(invitation=invitation, user=user).update(is_read=True)
    return invitation
