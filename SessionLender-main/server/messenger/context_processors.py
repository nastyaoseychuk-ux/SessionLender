from django.db.models import Q

from .models import ChatMembership, Profile
from friendships.models import Friendship

NAV_BY_URL_NAME = {
    'home': 'home',
    'rooms': 'rooms',
    'room-detail': 'rooms',
    'join-room': 'rooms',
    'people': 'people',
    'friends': 'friends',
    'user-profile': 'friends',
    'chats': 'chats',
    'chat-detail': 'chats',
    'notifications': 'chats',
    'admin-panel': 'admin',
    'analyst': 'analyst',
    'profile': 'profile',
}


def navigation(request):
    context = {'nav': NAV_BY_URL_NAME.get(getattr(request.resolver_match, 'url_name', None), '')}
    if request.user.is_authenticated:
        if getattr(request.resolver_match, 'url_name', None) in {'people', 'friends', 'user-profile', 'room-detail', 'chat-detail'}:
            # Один запит на обидва напрямки замість двох.
            friend_ids, following_ids = set(), set()
            follower_ids, pending_friend_ids = set(), set()
            my_id = request.user.pk
            for owner_id, friend_id, status in Friendship.objects.filter(
                Q(owner=request.user) | Q(friend=request.user)
            ).values_list('owner_id', 'friend_id', 'status'):
                if owner_id == my_id:
                    if status == Friendship.ACCEPTED:
                        friend_ids.add(friend_id)
                    else:
                        following_ids.add(friend_id)
                else:
                    if status != Friendship.ACCEPTED:
                        follower_ids.add(owner_id)
                    if status == Friendship.PENDING:
                        pending_friend_ids.add(owner_id)
            context['friend_ids'] = friend_ids
            context['following_ids'] = following_ids
            context['follower_ids'] = follower_ids
            context['pending_friend_ids'] = pending_friend_ids
        context['user_profile'] = Profile.for_user(request.user)
        context['unread_messages'] = ChatMembership.unread_total_for(request.user)
    return context
