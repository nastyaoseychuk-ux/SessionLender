from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from messenger.models import Notification, Profile
from messenger.notifications import publish
from messenger.security import is_rate_limited
from messenger.views import redirect_back
from .models import Friendship


@login_required
def index(request):
    query = request.GET.get('q', '').strip()
    find_friends = request.GET.get('filter') == 'find'
    requests_only = request.GET.get('filter') == 'requests'
    query_error = ''
    search_query = query[1:] if query.startswith('@') else query
    if find_friends and 'q' in request.GET:
        if query and not query.startswith('@'):
            query_error = 'Нікнейм має починатися із символу @. Наприклад: @nickname.'
        elif not search_query or '@' in search_query or any(c.isspace() for c in search_query):
            query_error = 'Введіть нікнейм після @ без пробілів. Наприклад: @nickname.'
        elif not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False) and is_rate_limited(
            request,
            'friend_search',
            getattr(settings, 'COMMENT_RATE_LIMIT', 20),
            getattr(settings, 'COMMENT_RATE_WINDOW', 60),
        ):
            # Пошук за підрядком — єдиний відкритий неадмінам спосіб перебору
            # акаунтів; обмежуємо його так само, як коментарі/повідомлення.
            query_error = 'Забагато спроб пошуку. Зачекайте хвилинку.'
    pending = Friendship.objects.filter(friend=request.user, status=Friendship.PENDING)
    if find_friends:
        ids = Profile.objects.filter(nickname__icontains=search_query, is_banned=False).exclude(user=request.user).values_list('user_id', flat=True) if search_query and not query_error else []
    elif requests_only:
        ids = pending.values_list('owner_id', flat=True)
    else:
        ids = Friendship.objects.filter(owner=request.user).values_list('friend_id', flat=True)
    profiles = Profile.objects.select_related('user').filter(user_id__in=ids, is_banned=False).order_by('nickname')
    if query:
        profiles = profiles.filter(Q(nickname__icontains=search_query) | Q(user__username__icontains=search_query))
    page = Paginator(profiles, 24).get_page(request.GET.get('page'))
    return render(request, 'friends.html', {
        'nav': 'friends', 'query': query, 'query_error': query_error, 'profiles': page.object_list,
        'page_obj': page, 'owned_rooms': request.user.created_rooms.all(),
        'requests_only': requests_only, 'find_friends': find_friends,
        'friend_request_count': pending.filter(owner__profile__is_banned=False).count(),
    })


def mark_request_read(link):
    if link.notification_id:
        Notification.objects.filter(pk=link.notification_id).update(is_read=True)


def send_request(owner, friend):
    link, created = Friendship.objects.get_or_create(owner=owner, friend=friend)
    if not created:
        return
    notice = Notification.objects.create(
        user=friend, actor=owner, kind=Notification.KIND_SYSTEM,
        text=f'Користувач @{Profile.for_user(owner).nickname} хоче з вами дружити',
    )
    link.notification = notice
    link.save(update_fields=['notification'])
    publish('friend_request', link.pk, [friend.pk])


def respond_to_request(owner, friend, action):
    incoming = get_object_or_404(Friendship, owner=friend, friend=owner, status=Friendship.PENDING)
    incoming.status = Friendship.ACCEPTED if action == 'accept' else Friendship.REJECTED
    incoming.save(update_fields=['status'])
    mark_request_read(incoming)
    if action == 'accept':
        reverse, _ = Friendship.objects.get_or_create(owner=owner, friend=friend)
        reverse.status = Friendship.ACCEPTED
        reverse.save(update_fields=['status'])
        mark_request_read(reverse)


def remove_relationship(owner, friend):
    outgoing = Friendship.objects.filter(owner=owner, friend=friend).first()
    if outgoing is None:
        return
    links = Friendship.objects.filter(pk=outgoing.pk)
    if outgoing.status == Friendship.ACCEPTED:
        links = Friendship.objects.filter(Q(owner=owner, friend=friend) | Q(owner=friend, friend=owner))
    notice_ids = list(links.exclude(notification_id=None).values_list('notification_id', flat=True))
    links.delete()
    Notification.objects.filter(pk__in=notice_ids).delete()


@login_required
@require_POST
def update(request, user_id):
    action = request.POST.get('friend_action')
    if action not in {'add', 'remove', 'accept', 'reject'} or user_id == request.user.pk:
        return HttpResponseBadRequest('Некоректна дія.')
    profile = get_object_or_404(Profile.objects.select_related('user'), user_id=user_id, is_banned=False)
    with transaction.atomic():
        # Lock both users in the same order, including simultaneous cross-requests.
        list(User.objects.select_for_update().filter(pk__in=[request.user.pk, user_id]).order_by('pk'))
        if action == 'add':
            send_request(request.user, profile.user)
            text = f'Ви стежите за @{profile.nickname}. Запит на дружбу надіслано.'
        elif action in {'accept', 'reject'}:
            respond_to_request(request.user, profile.user, action)
            text = 'Тепер ви друзі.' if action == 'accept' else 'Запит на дружбу відхилено.'
        else:
            remove_relationship(request.user, profile.user)
            text = 'Користувача видалено зі списку.'
    messages.success(request, text)
    return redirect_back(request, 'friends')
