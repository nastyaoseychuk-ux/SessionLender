import csv
import logging
import secrets
import string
from datetime import datetime, time, timedelta
from functools import wraps

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .invitations import invite_to_room, respond_to_invitation
from .audit import log_event
from .forms import (
    AddMemberForm,
    ChatMemberForm,
    ChatMessageEditForm,
    ChatMessageForm,
    CommentForm,
    GroupChatForm,
    LoginForm,
    NicknameForm,
    PostForm,
    ProfileSettingsForm,
    RegisterForm,
    RoomForm,
)
from .models import (
    AppSettings,
    AuditEvent,
    Chat,
    ChatAttachment,
    ChatMembership,
    ChatMessage,
    ChatReaction,
    Comment,
    Notification,
    Post,
    PostLike,
    Profile,
    Room,
    RoomInvitation,
    TemporaryCode,
)
from .realtime import (
    broadcast_message_deleted,
    broadcast_message_updated,
    broadcast_reactions,
    broadcast_read,
    mark_chat_notifications_read,
    message_for_broadcast,
    notify_chat_message,
    serialize_message,
    serialize_reactions,
)
from .security import is_locked, register_failure, reset_failures, is_rate_limited

ONLINE_WINDOW = timedelta(minutes=5)
CHAT_HISTORY_PAGE_SIZE = 30
GROUP_MEMBER_LIMIT = 50

logger = logging.getLogger(__name__)


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            profile = Profile.for_user(request.user)
            if profile.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def role_home(profile):
    if profile.role == Profile.ROLE_ADMIN:
        return 'admin-panel'
    if profile.role == Profile.ROLE_ANALYST:
        return 'analyst'
    return 'home'


def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def redirect_back(request, fallback_name, *fallback_args):
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect(fallback_name, *fallback_args)


def form_error_text(form):
    parts = []
    for field_errors in form.errors.values():
        parts.extend(field_errors)
    if not parts:
        parts.extend(form.non_field_errors())
    return ' '.join(parts)


def is_moderator(user):
    return Profile.for_user(user).role == Profile.ROLE_ADMIN


def can_create_groups(user):
    """Створення груп користувачами вмикається/вимикається адміном на панелі."""
    if is_moderator(user):
        return True
    allowed = (
        AppSettings.objects.filter(pk=1)
        .values_list('allow_user_group_creation', flat=True)
        .first()
    )
    return True if allowed is None else allowed


def throttle_identifier(request, nickname):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not ip:
        ip = request.META.get('REMOTE_ADDR', '')
    return f'{ip}:{(nickname or "").strip().lower()}'


def login_view(request):
    if request.user.is_authenticated:
        return redirect(role_home(Profile.for_user(request.user)))

    next_url = request.POST.get('next') or request.GET.get('next')
    nickname_attempt = (request.POST.get('nickname') or '').strip()
    identifier = throttle_identifier(request, nickname_attempt)
    locked = request.method == 'POST' and not request.POST.get('code') and is_locked(identifier)

    lock_minutes = max(1, settings.LOGIN_LOCKOUT_SECONDS // 60)
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and locked:
        form.add_error(None, f'Забагато невдалих спроб. Спробуйте через {lock_minutes} хв.')
        log_event(
            AuditEvent.ACTION_LOGIN_LOCKED,
            target=nickname_attempt or '—',
            detail='Спрацювало обмеження спроб входу.',
            request=request,
        )
    elif request.method == 'POST' and form.is_valid():
        reset_failures(identifier)
        if form.temporary_code:
            TemporaryCode.objects.filter(pk=form.temporary_code.pk).update(used=True)
            login(request, form.user, backend='django.contrib.auth.backends.ModelBackend')
            log_event(
                AuditEvent.ACTION_LOGIN_SUCCESS,
                actor=form.user,
                target=f'@{form.user.username}',
                detail='Вхід за тимчасовим кодом.',
                request=request,
            )
            messages.warning(request, 'Ви увійшли за тимчасовим кодом. Змініть пароль у налаштуваннях.')
            return redirect('profile')
        login(request, form.user)
        log_event(
            AuditEvent.ACTION_LOGIN_SUCCESS,
            actor=form.user,
            target=f'@{form.user.username}',
            request=request,
        )
        messages.success(request, f'Вітаємо, @{form.user.username}!')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(role_home(Profile.for_user(form.user)))
    elif request.method == 'POST':
        attempts = register_failure(identifier)
        log_event(
            AuditEvent.ACTION_LOGIN_FAILED,
            target=nickname_attempt or '—',
            detail=f'Невдала спроба входу ({attempts}).',
            request=request,
        )
        if is_locked(identifier):
            form.add_error(None, f'Забагато невдалих спроб. Спробуйте через {lock_minutes} хв.')
    return render(request, 'auth.html', {'form': form, 'mode': 'login', 'next_url': next_url})


def register_view(request):
    if request.user.is_authenticated:
        return redirect(role_home(Profile.for_user(request.user)))

    next_url = request.POST.get('next') or request.GET.get('next')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        log_event(
            AuditEvent.ACTION_REGISTER,
            actor=user,
            target=f'@{user.username}',
            request=request,
        )
        messages.success(request, 'Акаунт створено. Ласкаво просимо!')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect('home')
    return render(request, 'auth.html', {'form': form, 'mode': 'register', 'next_url': next_url})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def home(request):
    query = request.GET.get('q', '').strip()
    rooms = Room.objects.filter(pk__in=request.user.rooms.values('pk')).annotate(
        member_count=Count('members', distinct=True),
        post_count=Count('posts', distinct=True),
    )
    posts = (
        Post.objects.select_related('author', 'author__profile', 'room')
        .annotate(like_count=Count('likes', distinct=True))
        .prefetch_related(
            'comments__author',
            'comments__author__profile',
            Prefetch('likes', queryset=PostLike.objects.filter(user=request.user), to_attr='my_likes'),
        )
        .filter(room__members=request.user)
    )
    if query:
        posts = posts.filter(
            Q(caption__icontains=query)
            | Q(author__username__icontains=query)
            | Q(room__name__icontains=query)
        )

    posts = posts.order_by('-created_at')
    paginator = Paginator(posts, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    post_form = PostForm(user=request.user) if rooms.exists() else None
    active_people = (
        Profile.objects.select_related('user')
        .filter(is_banned=False, last_seen__gte=timezone.now() - ONLINE_WINDOW)
        .exclude(user=request.user)
        .order_by('-last_seen')
    )
    if Profile.for_user(request.user).role != Profile.ROLE_ADMIN:
        from friendships.models import Friendship

        friend_ids = Friendship.objects.filter(
            owner=request.user, status=Friendship.ACCEPTED,
        ).values_list('friend_id', flat=True)
        active_people = active_people.filter(user_id__in=friend_ids)
    active_people = active_people[:5]
    return render(
        request,
        'home.html',
        {
            'page_obj': page_obj,
            'posts': page_obj.object_list,
            'rooms': rooms,
            'post_form': post_form,
            'query': query,
            'has_rooms': post_form is not None,
            'active_people': active_people,
        },
    )


def pending_room_invitations(user):
    return RoomInvitation.objects.filter(user=user, status=RoomInvitation.PENDING).select_related('room', 'inviter')


@login_required
@require_POST
def room_invitation_response(request, invitation_id):
    action = request.POST.get('action')
    if action not in ('accept', 'reject'):
        return HttpResponse('Некоректна дія.', status=400)
    invitation = respond_to_invitation(invitation_id, request.user, action)
    if invitation.status == RoomInvitation.ACCEPTED:
        messages.success(request, f'Ви приєдналися до кімнати «{invitation.room.name}».')
    else:
        messages.success(request, 'Запрошення відхилено.')
    destination = 'notifications' if request.POST.get('source') == 'notifications' else 'rooms'
    return redirect(destination)


@login_required
def rooms_view(request):
    rooms = Room.objects.filter(pk__in=request.user.rooms.values('pk')).annotate(
        member_count=Count('members', distinct=True),
        post_count=Count('posts', distinct=True),
    )
    invitee = None
    invitee_id = request.GET.get('invitee')
    if invitee_id:
        if not invitee_id.isdigit():
            raise Http404
        invitee = get_object_or_404(
            RoomForm.base_fields['invitee'].queryset,
            pk=int(invitee_id),
        )
    form = RoomForm(initial={'invitee': invitee})
    return render(request, 'rooms.html', {'rooms': rooms, 'form': form, 'invitee': invitee,
        'room_invitations': pending_room_invitations(request.user)})


@login_required
@require_POST
@transaction.atomic
def create_room(request):
    if not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
        if is_rate_limited(request, 'room_create', getattr(settings, 'ROOM_CREATE_RATE_LIMIT', 5), getattr(settings, 'ROOM_CREATE_RATE_WINDOW', 3600)):
            messages.error(request, 'Забагато спроб створення кімнат. Спробуйте пізніше.')
            return redirect('rooms')
    form = RoomForm(request.POST, request.FILES)
    if form.is_valid():
        room = form.save(commit=False)
        room.created_by = request.user
        room.save()
        room.members.add(request.user)
        invitee = form.cleaned_data.get('invitee')
        if invitee is not None:
            invite_to_room(room, request.user, invitee)
        log_event(
            AuditEvent.ACTION_ROOM_CREATED,
            actor=request.user,
            target=room.name,
            request=request,
        )
        messages.success(request, f'Кімнату «{room.name}» створено.')
        return redirect('room-detail', room.pk)
    rooms = Room.objects.filter(pk__in=request.user.rooms.values('pk')).annotate(
        member_count=Count('members', distinct=True),
        post_count=Count('posts', distinct=True),
    )
    return render(request, 'rooms.html', {
        'rooms': rooms,
        'form': form,
        'invitee': form.cleaned_data.get('invitee'),
        'room_invitations': pending_room_invitations(request.user),
    }, status=400)


@login_required
def room_detail(request, room_id):
    room = get_object_or_404(
        Room.objects.select_related('created_by').prefetch_related('members__profile'),
        pk=room_id,
    )
    if not room.is_member(request.user):
        raise PermissionDenied

    posts = (
        room.posts.select_related('author', 'author__profile').order_by('-created_at', '-pk')
        .annotate(like_count=Count('likes', distinct=True))
        .prefetch_related(
            'comments__author',
            'comments__author__profile',
            Prefetch('likes', queryset=PostLike.objects.filter(user=request.user), to_attr='my_likes'),
        )
    )
    post_form = PostForm(user=request.user, initial={'room': room})
    post_form.fields['room'].widget = forms.HiddenInput()
    add_member_form = AddMemberForm(user=request.user, initial={'room': room}) if room.is_owner(request.user) else None
    invite_url = None
    if room.is_owner(request.user):
        invite_url = request.build_absolute_uri(
            reverse('join-room', args=[room.invite_token])
        )
    return render(
        request,
        'room_detail.html',
        {
            'room': room,
            'posts': posts,
            'post_form': post_form,
            'add_member_form': add_member_form,
            'members': room.members.select_related('profile').all(),
            'invite_url': invite_url,
            'can_create_groups': can_create_groups(request.user),
        },
    )


@login_required
@require_POST
def delete_room(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if not room.is_owner(request.user):
        raise PermissionDenied
    name = room.name
    room.delete()
    log_event(
        AuditEvent.ACTION_ROOM_DELETED,
        actor=request.user,
        target=name,
        request=request,
    )
    messages.success(request, f'Кімнату «{name}» видалено.')
    return redirect('rooms')


@login_required
@require_POST
def leave_room(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if not room.is_member(request.user):
        raise PermissionDenied
    if room.is_owner(request.user):
        messages.error(request, 'Власник не може залишити кімнату. Видаліть її або передайте іншому учаснику.')
        return redirect('room-detail', room.pk)
    room.members.remove(request.user)
    messages.success(request, f'Ви залишили кімнату «{room.name}».')
    return redirect('rooms')


@login_required
def join_room(request, token):
    room = get_object_or_404(
        Room.objects.select_related('created_by').annotate(
            member_count=Count('members', distinct=True),
            post_count=Count('posts', distinct=True),
        ),
        invite_token=token,
    )
    if room.is_member(request.user):
        return redirect('room-detail', room.pk)

    if request.method == 'POST':
        room.members.add(request.user)
        log_event(
            AuditEvent.ACTION_ROOM_JOINED,
            actor=request.user,
            target=room.name,
            detail='Приєднання за посиланням-запрошенням.',
            request=request,
        )
        messages.success(request, f'Ви приєдналися до кімнати «{room.name}».')
        return redirect('room-detail', room.pk)

    return render(request, 'join_room.html', {'room': room})


@login_required
@require_POST
def regenerate_invite(request, room_id):
    room = get_object_or_404(Room, pk=room_id, created_by=request.user)
    room.regenerate_invite_token()
    log_event(
        AuditEvent.ACTION_ROOM_INVITE_RESET,
        actor=request.user,
        target=room.name,
        request=request,
    )
    messages.success(request, 'Посилання-запрошення оновлено. Старе більше не діє.')
    return redirect('room-detail', room.pk)


def _add_member(request, room=None):
    data = request.POST.copy()
    if room is not None:
        data['room'] = room.pk
    form = AddMemberForm(request.user, data)
    if form.is_valid():
        target = form.save()
        messages.success(request, f'@{target.username} запрошено до кімнати «{form.cleaned_data["room"].name}».')
    else:
        messages.error(request, form_error_text(form))
    if room is not None:
        return redirect('room-detail', room.pk)
    return redirect_back(request, 'people')


@login_required
@require_POST
def add_member(request, room_id):
    room = get_object_or_404(Room, pk=room_id, created_by=request.user)
    return _add_member(request, room=room)


@login_required
@require_POST
def add_member_from_people(request):
    return _add_member(request)


@login_required
@require_POST
def remove_member(request, room_id, user_id):
    room = get_object_or_404(Room, pk=room_id, created_by=request.user)
    member = get_object_or_404(User, pk=user_id)
    if member.pk == room.created_by_id:
        messages.error(request, 'Не можна вилучити власника кімнати.')
    else:
        room.members.remove(member)
        messages.success(request, f'@{member.username} вилучено з кімнати.')
    return redirect('room-detail', room.pk)


@login_required
@require_POST
def create_post(request):
    if not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
        if is_rate_limited(request, 'post_create', getattr(settings, 'COMMENT_RATE_LIMIT', 20), getattr(settings, 'COMMENT_RATE_WINDOW', 60)):
            messages.error(request, 'Забагато дій. Спробуйте пізніше.')
            return redirect_back(request, 'home')
    form = PostForm(request.user, request.POST, request.FILES)
    if form.is_valid():
        post = form.save()
        messages.success(request, 'Допис опубліковано.')
        return redirect('room-detail', post.room_id)
    messages.error(request, form_error_text(form))
    return redirect_back(request, 'home')


@login_required
@require_POST
def add_comment(request, post_id):
    if not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
        if is_rate_limited(request, 'comment_create', getattr(settings, 'COMMENT_RATE_LIMIT', 20), getattr(settings, 'COMMENT_RATE_WINDOW', 60)):
            post = get_object_or_404(Post.objects.select_related('room'), pk=post_id)
            messages.error(request, 'Забагато дій. Спробуйте пізніше.')
            return redirect_back(request, 'room-detail', post.room_id)
    post = get_object_or_404(Post.objects.select_related('room'), pk=post_id)
    if not post.room.is_member(request.user):
        raise PermissionDenied

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
    else:
        messages.error(request, form_error_text(form))
    return redirect_back(request, 'room-detail', post.room_id)


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(
        Comment.objects.select_related('post__room', 'author'),
        pk=comment_id,
    )
    room = comment.post.room
    moderator = is_moderator(request.user)
    allowed = (
        comment.author_id == request.user.pk
        or room.is_owner(request.user)
        or moderator
    )
    if not allowed:
        raise PermissionDenied
    if not room.is_member(request.user) and not moderator:
        raise PermissionDenied

    author_name = comment.author.username
    comment.delete()
    log_event(
        AuditEvent.ACTION_COMMENT_DELETED,
        actor=request.user,
        target=f'@{author_name}',
        detail=f'Кімната «{room.name}».',
        request=request,
    )
    messages.success(request, 'Коментар видалено.')
    return redirect_back(request, 'room-detail', room.pk)


@login_required
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post.objects.select_related('room', 'author'), pk=post_id)
    moderator = is_moderator(request.user)
    if post.author_id != request.user.pk and not moderator:
        raise PermissionDenied
    if not post.room.is_member(request.user) and not moderator:
        raise PermissionDenied
    room_id = post.room_id
    author_name = post.author.username
    post.delete()
    log_event(
        AuditEvent.ACTION_POST_DELETED,
        actor=request.user,
        target=f'@{author_name}',
        detail=f'Кімната «{post.room.name}».',
        request=request,
    )
    messages.success(request, 'Допис видалено.')
    return redirect_back(request, 'room-detail', room_id)


@login_required
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post.objects.select_related('room'), pk=post_id)
    if not post.room.is_member(request.user):
        raise PermissionDenied
    like, created = PostLike.objects.get_or_create(post=post, user=request.user)
    if not created:
        like.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'liked': created,
                'count': PostLike.objects.filter(post=post).count(),
            }
        )
    return redirect_back(request, 'room-detail', post.room_id)


@login_required
def chats(request):
    last_message_subquery = (
        ChatMessage.objects.filter(chat=OuterRef('chat_id'))
        .order_by('-created_at')
        .values('pk')[:1]
    )
    unread_subquery = (
        ChatMessage.objects.filter(
            chat=OuterRef('chat_id'),
            created_at__gt=OuterRef('last_read_at'),
        )
        .exclude(author=request.user)
        .values('chat_id')
        .annotate(c=Count('pk'))
        .values('c')
    )
    memberships = list(
        ChatMembership.objects.filter(user=request.user)
        .select_related('chat')
        .annotate(
            last_message_id=Subquery(last_message_subquery),
            unread_count=Subquery(unread_subquery),
        )
        .prefetch_related('chat__memberships__user__profile')
        .order_by('-chat__updated_at')
    )
    chat_ids = [m.chat_id for m in memberships]
    last_messages = {}
    last_ids = [m.last_message_id for m in memberships if m.last_message_id]
    if last_ids:
        for msg in (
            ChatMessage.objects.filter(pk__in=last_ids)
            .select_related('author', 'author__profile')
            .prefetch_related('attachments')
        ):
            last_messages[msg.pk] = msg
    member_counts = dict(
        ChatMembership.objects.filter(chat_id__in=chat_ids)
        .values('chat_id')
        .annotate(c=Count('pk'))
        .values_list('chat_id', 'c')
    )

    entries = []
    for membership in memberships:
        chat = membership.chat
        last = last_messages.get(membership.last_message_id) if membership.last_message_id else None
        other = None if chat.is_group else membership.other_user
        entries.append(
            {
                'chat': chat,
                'title': chat.display_title(request.user),
                'is_group': chat.is_group,
                'member_count': member_counts.get(chat.pk, 0),
                'other': other,
                'last': last,
                'unread': membership.unread_count or 0,
            }
        )
    return render(
        request,
        'chats.html',
        {
            'entries': entries,
            'group_form': GroupChatForm(request.user),
            'can_create_groups': can_create_groups(request.user),
        },
    )


def _chat_messages_for_view(chat, user):
    queryset = (
        chat.messages.select_related(
            'author',
            'author__profile',
            'reply_to__author',
        )
        .prefetch_related('attachments', 'reactions')
        .order_by('-created_at')
    )
    window = list(queryset[: CHAT_HISTORY_PAGE_SIZE + 1])
    has_earlier = len(window) > CHAT_HISTORY_PAGE_SIZE
    messages_list = list(reversed(window[:CHAT_HISTORY_PAGE_SIZE]))
    for message in messages_list:
        message.ui_reactions = serialize_reactions(message, user)
    return messages_list, has_earlier


@login_required
def chat_detail(request, chat_id):
    membership = get_object_or_404(
        ChatMembership.objects.select_related('chat').prefetch_related(
            'chat__memberships__user__profile'
        ),
        chat_id=chat_id,
        user=request.user,
    )
    chat = membership.chat
    if request.method == 'POST':
        if not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
            if is_rate_limited(request, 'chat_message', getattr(settings, 'MESSAGE_RATE_LIMIT', 30), getattr(settings, 'MESSAGE_RATE_WINDOW', 60)):
                messages.error(request, 'Забагато повідомлень. Спробуйте пізніше.')
                return redirect('chat-detail', chat_id)
        form = ChatMessageForm(request.POST, request.FILES, chat=chat)
        if form.is_valid():
            if form.attachment_specs and not getattr(settings, 'TEST', False) and not getattr(request, '_skip_rate_limit', False):
                if is_rate_limited(request, 'chat_upload', getattr(settings, 'UPLOAD_RATE_LIMIT', 10), getattr(settings, 'UPLOAD_RATE_WINDOW', 60)):
                    messages.error(request, 'Забагато завантажень. Спробуйте пізніше.')
                    return redirect('chat-detail', chat_id)
            try:
                with transaction.atomic():
                    message = form.save(commit=False)
                    message.chat = chat
                    message.author = request.user
                    message.reply_to = form.cleaned_data.get('reply_to')
                    message.save()
                    for spec in form.attachment_specs:
                        ChatAttachment.objects.create(
                            message=message,
                            file=spec['upload'],
                            kind=spec['kind'],
                            original_name=spec['original_name'],
                            content_type=spec['content_type'],
                            size=spec['size'],
                            duration_seconds=spec.get('duration_seconds'),
                        )
            except Exception:
                # Сховище (напр. Vercel Blob) відмовило — повертаємо зрозумілу
                # помилку замість «Server Error (500)»; деталі — у логах/Sentry.
                logger.exception('Не вдалося зберегти повідомлення з вкладенням.')
                messages.error(request, 'Не вдалося надіслати файл. Спробуйте ще раз.')
            else:
                notify_chat_message(message)
                return redirect('chat-detail', chat.pk)
        else:
            messages.error(request, form_error_text(form))
    else:
        form = ChatMessageForm(chat=chat)

    other_membership = None
    if not chat.is_group:
        other_membership = chat.memberships.exclude(user=request.user).first()
    other_last_read = other_membership.last_read_at if other_membership else None
    chat_messages, has_earlier = _chat_messages_for_view(chat, request.user)
    read_at = timezone.now()
    ChatMembership.objects.filter(pk=membership.pk).update(last_read_at=read_at)
    mark_chat_notifications_read(chat.pk, request.user)
    broadcast_read(chat.pk, request.user.pk, read_at)
    return render(
        request,
        'chat_detail.html',
        {
            'chat': chat,
            'other': None if chat.is_group else membership.other_user,
            'other_last_read': other_last_read,
            'can_moderate_chat': is_moderator(request.user),
            'chat_messages': chat_messages,
            'chat_last': chat_messages[-1] if chat_messages else None,
            'has_earlier': has_earlier,
            'form': form,
            'chat_member_form': ChatMemberForm(chat) if chat.can_manage(request.user) else None,
            'chat_memberships': chat.memberships.select_related('user__profile').all() if chat.is_group else [],
        },
    )


@login_required
def chat_history(request, chat_id):
    membership = get_object_or_404(ChatMembership, chat_id=chat_id, user=request.user)
    chat = membership.chat
    before = request.GET.get('before', '')
    queryset = (
        chat.messages.select_related('author', 'author__profile', 'reply_to__author')
        .prefetch_related('attachments', 'reactions')
        .order_by('-created_at')
    )
    if before.isdigit():
        queryset = queryset.filter(pk__lt=int(before))
    window = list(queryset[: CHAT_HISTORY_PAGE_SIZE + 1])
    has_more = len(window) > CHAT_HISTORY_PAGE_SIZE
    messages_list = list(reversed(window[:CHAT_HISTORY_PAGE_SIZE]))
    return JsonResponse(
        {
            'messages': [serialize_message(message, request.user) for message in messages_list],
            'has_more': has_more,
        }
    )


@login_required
def chat_poll(request, chat_id):
    membership = get_object_or_404(
        ChatMembership.objects.select_related('chat'), chat_id=chat_id, user=request.user
    )
    chat = membership.chat
    after_raw = request.GET.get('after', '')
    after = parse_datetime(after_raw) if after_raw else None
    if after and timezone.is_naive(after):
        after = timezone.make_aware(after)

    latest_created = (
        chat.messages.order_by('-created_at').values_list('created_at', flat=True).first()
    )
    # Шлях без нових повідомлень: жодних UPDATE/серіалізації — це 95% опитувань
    # і майже вся навантаження на функції Vercel (poll кожні 3 с з відкритого чату).
    if after is not None and (latest_created is None or latest_created <= after):
        return JsonResponse({'messages': [], 'last': after_raw})

    other_membership = None
    if not chat.is_group:
        other_membership = chat.memberships.exclude(user=request.user).first()
    other_last_read = other_membership.last_read_at if other_membership else None

    items = (
        chat.messages.select_related('author', 'author__profile', 'reply_to__author')
        .prefetch_related('attachments', 'reactions')
    )
    if after is not None:
        items = items.filter(created_at__gt=after)
    payload = [serialize_message(message, request.user, other_last_read) for message in items]

    ChatMembership.objects.filter(pk=membership.pk).update(last_read_at=timezone.now())
    mark_chat_notifications_read(chat.pk, request.user)
    return JsonResponse(
        {
            'messages': payload,
            'last': latest_created.isoformat() if latest_created else after_raw,
        }
    )


@login_required
@require_POST
def delete_chat_message(request, message_id):
    message = get_object_or_404(
        ChatMessage.objects.select_related('chat', 'author'),
        pk=message_id,
    )
    membership = ChatMembership.objects.filter(chat=message.chat, user=request.user).first()
    if membership is None:
        raise PermissionDenied
    if (
        message.author_id != request.user.pk
        and not is_moderator(request.user)
        and not (membership.can_manage)
    ):
        raise PermissionDenied

    chat_id = message.chat_id
    author_name = message.author.username
    message.delete()
    broadcast_message_deleted(chat_id, message_id)
    log_event(
        AuditEvent.ACTION_MESSAGE_DELETED,
        actor=request.user,
        target=f'@{author_name}',
        detail=f'Чат #{chat_id}.',
        request=request,
    )
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'deleted': True, 'message_id': message_id})
    messages.success(request, 'Повідомлення видалено.')
    return redirect('chat-detail', chat_id)


@login_required
@require_POST
def edit_chat_message(request, message_id):
    message = get_object_or_404(
        ChatMessage.objects.select_related('chat', 'author'),
        pk=message_id,
    )
    if not ChatMembership.objects.filter(chat=message.chat, user=request.user).exists():
        raise PermissionDenied
    if message.author_id != request.user.pk:
        raise PermissionDenied

    form = ChatMessageEditForm(request.POST, message=message)
    if not form.is_valid():
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'errors': form.errors}, status=400)
        messages.error(request, form_error_text(form))
        return redirect('chat-detail', message.chat_id)
    form.save()
    fresh = message_for_broadcast(message)
    broadcast_message_updated(fresh)
    log_event(
        AuditEvent.ACTION_MESSAGE_EDITED,
        actor=request.user,
        target=f'@{message.author.username}',
        detail=f'Чат #{message.chat_id}.',
        request=request,
    )
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(serialize_message(fresh, request.user))
    messages.success(request, 'Повідомлення оновлено.')
    return redirect('chat-detail', message.chat_id)


@login_required
@require_POST
def toggle_chat_reaction(request, message_id):
    message = get_object_or_404(ChatMessage.objects.select_related('chat'), pk=message_id)
    if not ChatMembership.objects.filter(chat=message.chat, user=request.user).exists():
        raise PermissionDenied
    emoji = (request.POST.get('emoji') or '').strip()
    if emoji not in ChatReaction.ALLOWED_EMOJIS:
        return JsonResponse({'error': 'Непідтримувана реакція.'}, status=400)
    reaction = ChatReaction.objects.filter(
        message=message,
        user=request.user,
        emoji=emoji,
    ).first()
    if reaction is not None:
        reaction.delete()
    else:
        ChatReaction.objects.create(message=message, user=request.user, emoji=emoji)
    broadcast_reactions(message.chat_id, message)
    return JsonResponse(
        {
            'message_id': message.pk,
            'reactions': serialize_reactions(message, request.user),
        }
    )


@login_required
@require_POST
def create_group_chat(request):
    if not can_create_groups(request.user):
        messages.error(request, 'Створення груп вимкнено адміністратором.')
        return redirect('chats')
    form = GroupChatForm(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, form_error_text(form))
        return redirect('chats')
    chat = form.save()
    log_event(
        AuditEvent.ACTION_GROUP_CREATED,
        actor=request.user,
        target=chat.title,
        request=request,
    )
    messages.success(request, f'Групу «{chat.title}» створено.')
    return redirect('chat-detail', chat.pk)


@login_required
@require_POST
def create_room_group(request, room_id):
    """Груповий чат з усіма учасниками кімнати — одним кліком."""
    if not can_create_groups(request.user):
        messages.error(request, 'Створення груп вимкнено адміністратором.')
        return redirect('chats')
    room = get_object_or_404(Room, pk=room_id)
    if not room.is_member(request.user):
        raise PermissionDenied
    members = list(
        room.members.filter(is_active=True, profile__is_banned=False).exclude(pk=request.user.pk)
    )
    if not members:
        messages.error(request, 'У кімнаті немає інших активних учасників для групи.')
        return redirect('room-detail', room.pk)
    if len(members) > GROUP_MEMBER_LIMIT:
        messages.error(
            request,
            f'У кімнаті забагато учасників для групи (максимум {GROUP_MEMBER_LIMIT}).',
        )
        return redirect('room-detail', room.pk)
    title = (room.name or '').strip() or f'Група №{room.pk}'
    chat = Chat.create_group(request.user, title, members)
    log_event(
        AuditEvent.ACTION_GROUP_CREATED,
        actor=request.user,
        target=chat.title,
        detail=f'Створено з кімнати «{room.name}» ({len(members) + 1} учасників).',
        request=request,
    )
    messages.success(request, f'Групу «{chat.title}» створено з усіма учасниками кімнати.')
    return redirect('chat-detail', chat.pk)


@login_required
@require_POST
def add_chat_member(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, kind=Chat.KIND_GROUP)
    if not chat.can_manage(request.user):
        raise PermissionDenied
    form = ChatMemberForm(chat, request.POST)
    if not form.is_valid():
        messages.error(request, form_error_text(form))
    else:
        membership = form.save()
        log_event(
            AuditEvent.ACTION_GROUP_MEMBER_ADDED,
            actor=request.user,
            target=f'@{membership.user.username}',
            detail=f'Група «{chat.title}».',
            request=request,
        )
        messages.success(request, f'@{membership.user.username} додано до групи.')
    return redirect('chat-detail', chat.pk)


@login_required
@require_POST
def remove_chat_member(request, chat_id, user_id):
    chat = get_object_or_404(Chat, pk=chat_id, kind=Chat.KIND_GROUP)
    membership = chat.membership_for(request.user)
    if membership is None:
        raise PermissionDenied
    target = get_object_or_404(ChatMembership, chat=chat, user_id=user_id)
    if target.role == ChatMembership.ROLE_OWNER:
        messages.error(request, 'Власника групи не можна вилучити.')
    elif membership.role == ChatMembership.ROLE_ADMIN and target.role == ChatMembership.ROLE_ADMIN:
        messages.error(request, 'Адміністратор не може вилучити іншого адміністратора.')
    elif not membership.can_manage:
        raise PermissionDenied
    else:
        target.delete()
        messages.success(request, 'Учасника вилучено з групи.')
    return redirect('chat-detail', chat.pk)


@login_required
@require_POST
def leave_chat(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, kind=Chat.KIND_GROUP)
    membership = chat.membership_for(request.user)
    if membership is None:
        raise PermissionDenied
    if membership.role == ChatMembership.ROLE_OWNER:
        messages.error(request, 'Власник не може залишити групу. Видаліть її.')
    else:
        membership.delete()
        messages.success(request, f'Ви залишили групу «{chat.title}».')
    return redirect('chats')


@login_required
@require_POST
def delete_group_chat(request, chat_id):
    chat = get_object_or_404(Chat, pk=chat_id, kind=Chat.KIND_GROUP)
    membership = chat.membership_for(request.user)
    if membership is None or membership.role != ChatMembership.ROLE_OWNER:
        raise PermissionDenied
    title = chat.title
    chat.delete()
    messages.success(request, f'Групу «{title}» видалено.')
    return redirect('chats')


@login_required
def notifications_view(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'clear_old':
            cutoff = timezone.now() - timedelta(days=30)
            Notification.objects.filter(user=request.user, created_at__lt=cutoff).delete()
            messages.success(request, 'Старі сповіщення видалено.')
            return redirect('notifications')
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, 'Усі сповіщення позначено прочитаними.')
        return redirect('notifications')
    from .notification_list import grouped_notifications, prepare_notice

    show_all = request.GET.get('all') == '1'
    paginator = Paginator(grouped_notifications(request.user), 20 if show_all else 10)
    page = paginator.get_page(request.GET.get('page') if show_all else 1)
    return render(request, 'notifications.html', {
        'notifications': [prepare_notice(item) for item in page],
        'page_obj': page,
        'show_all': show_all,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
    })


@login_required
def chat_attachment(request, attachment_id):
    attachment = get_object_or_404(
        ChatAttachment.objects.select_related('message'),
        pk=attachment_id,
    )
    if not ChatMembership.objects.filter(
        chat_id=attachment.message.chat_id,
        user=request.user,
    ).exists():
        raise PermissionDenied
    try:
        file_handle = attachment.file.open('rb')
    except (FileNotFoundError, ValueError):
        raise Http404
    content_type = attachment.content_type or 'application/octet-stream'
    as_attachment = attachment.kind == ChatAttachment.KIND_FILE
    if as_attachment:
        content_type = 'application/octet-stream'
    response = FileResponse(
        file_handle,
        content_type=content_type,
        as_attachment=as_attachment,
        filename=attachment.original_name,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
def start_chat(request, user_id):
    other = get_object_or_404(User, pk=user_id)
    if other.pk == request.user.pk:
        messages.error(request, 'Не можна написати самому собі.')
        return redirect_back(request, 'chats')
    other_profile = Profile.for_user(other)
    if other_profile.is_banned:
        messages.error(request, 'Цей користувач заблокований.')
        return redirect_back(request, 'chats')
    chat, _ = Chat.between(request.user, other)
    return redirect('chat-detail', chat.pk)


@role_required(Profile.ROLE_ADMIN)
def people(request):
    query = request.GET.get('q', '').strip()
    profiles = (
        Profile.objects.select_related('user')
        .filter(is_banned=False)
        .exclude(user=request.user)
    )
    if query:
        profiles = profiles.filter(Q(nickname__icontains=query) | Q(user__username__icontains=query))
    profiles = profiles.order_by('nickname')
    paginator = Paginator(profiles, 24)
    page_obj = paginator.get_page(request.GET.get('page'))
    owned_rooms = request.user.created_rooms.all()
    return render(
        request,
        'people.html',
        {
            'profiles': page_obj.object_list,
            'page_obj': page_obj,
            'query': query,
            'owned_rooms': owned_rooms,
        },
    )


@login_required
def user_profile(request, nickname):
    profile = get_object_or_404(
        Profile.objects.select_related('user'),
        nickname__iexact=nickname,
    )
    if profile.is_banned and not is_moderator(request.user):
        raise Http404

    is_self = profile.user_id == request.user.pk
    shared_rooms = (
        Room.objects.filter(
            pk__in=Room.objects.filter(
                members=profile.user, pk__in=request.user.rooms.values('pk'),
            ).values('pk'),
        )
        .annotate(
            member_count=Count('members', distinct=True),
            post_count=Count('posts', distinct=True),
        )
        .order_by('name')
    )
    recent_posts = (
        Post.objects.filter(author=profile.user, room__members=request.user)
        .select_related('room')
        .order_by('-created_at')
        .distinct()[:6]
    )
    stats = {
        'rooms': profile.user.rooms.count(),
        'posts': Post.objects.filter(author=profile.user).count(),
        'comments': Comment.objects.filter(author=profile.user).count(),
        'messages': ChatMessage.objects.filter(author=profile.user).count(),
        'likes': PostLike.objects.filter(post__author=profile.user).count(),
    }
    return render(
        request,
        'user_profile.html',
        {
            'profile': profile,
            'person': profile.user,
            'is_self': is_self,
            'shared_rooms': shared_rooms,
            'recent_posts': recent_posts,
            'stats': stats,
            'owned_rooms': request.user.created_rooms.all() if not is_self else Room.objects.none(),
        },
    )


@login_required
def profile_view(request):
    profile = Profile.for_user(request.user)
    nickname_form = NicknameForm(request.user)
    password_form = PasswordChangeForm(request.user)
    settings_form = ProfileSettingsForm(instance=profile)

    if request.method == 'POST':
        if request.POST.get('form') == 'nickname':
            nickname_form = NicknameForm(request.user, request.POST)
            if nickname_form.is_valid():
                nickname_form.save()
                messages.success(request, 'Нікнейм оновлено.')
                return redirect('profile')
        elif request.POST.get('form') == 'password':
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Пароль змінено.')
                return redirect('profile')
        elif request.POST.get('form') == 'settings':
            settings_form = ProfileSettingsForm(request.POST, request.FILES, instance=profile)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, 'Профіль оновлено.')
                return redirect('profile')
        else:
            messages.error(request, 'Невідома дія.')

    return render(
        request,
        'profile.html',
        {
            'profile': profile,
            'nickname_form': nickname_form,
            'password_form': password_form,
            'settings_form': settings_form,
            'likes_received': PostLike.objects.filter(post__author=request.user).count(),
        },
    )


@role_required(Profile.ROLE_ADMIN)
def admin_panel(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'toggle-group-creation':
            app_settings = AppSettings.load()
            app_settings.allow_user_group_creation = not app_settings.allow_user_group_creation
            app_settings.save(update_fields=['allow_user_group_creation'])
            state = 'увімкнено' if app_settings.allow_user_group_creation else 'вимкнено'
            log_event(
                AuditEvent.ACTION_SETTINGS_CHANGED,
                actor=request.user,
                target='Створення груп користувачами',
                detail=f'{state}.',
                request=request,
            )
            messages.success(request, f'Створення груп користувачами {state}.')
            return redirect('admin-panel')
        profile_id = request.POST.get('profile_id')
        if not profile_id or not str(profile_id).isdigit():
            messages.error(request, 'Некоректний користувач.')
            return redirect('admin-panel')
        profile = get_object_or_404(Profile.objects.select_related('user'), pk=profile_id)
        action = request.POST.get('action')
        is_self = profile.user_id == request.user.pk

        if profile.user.is_superuser and not is_self:
            messages.error(request, 'Керувати суперкористувачем можна лише через Django Admin.')
            return redirect('admin-panel')
        if is_self and action in {'reset-password', 'create-code'}:
            messages.error(request, 'Для власного акаунта використовуйте сторінку налаштувань.')
            return redirect('admin-panel')

        if action == 'toggle-ban':
            if is_self:
                messages.error(request, 'Не можна заблокувати власний акаунт.')
            elif profile.user.is_superuser:
                messages.error(request, 'Суперкористувача не можна заблокувати.')
            else:
                profile.is_banned = not profile.is_banned
                profile.save(update_fields=['is_banned'])
                state = 'заблоковано' if profile.is_banned else 'розблоковано'
                log_event(
                    AuditEvent.ACTION_USER_BANNED if profile.is_banned else AuditEvent.ACTION_USER_UNBANNED,
                    actor=request.user,
                    target=f'@{profile.nickname}',
                    request=request,
                )
                messages.success(request, f'Акаунт @{profile.nickname} {state}.')
        elif action == 'set-role':
            role = request.POST.get('role')
            if is_self:
                messages.error(request, 'Не можна змінити власну роль.')
            elif profile.user.is_superuser:
                messages.error(request, 'Роль суперкористувача змінити неможливо.')
            elif role not in dict(Profile.ROLE_CHOICES):
                messages.error(request, 'Невідома роль.')
            else:
                previous_role = profile.get_role_display()
                user = profile.user
                user.is_staff = role == Profile.ROLE_ADMIN
                user.save(update_fields=['is_staff'])
                profile.role = role
                profile.save(update_fields=['role'])
                log_event(
                    AuditEvent.ACTION_ROLE_CHANGED,
                    actor=request.user,
                    target=f'@{profile.nickname}',
                    detail=f'{previous_role} → {profile.get_role_display()}.',
                    request=request,
                )
                messages.success(request, f'Роль @{profile.nickname} змінено на «{profile.get_role_display()}».')
        elif action == 'reset-password':
            password = generate_password()
            profile.user.set_password(password)
            profile.user.save(update_fields=['password'])
            TemporaryCode.objects.filter(user=profile.user, used=False).update(used=True)
            log_event(
                AuditEvent.ACTION_PASSWORD_RESET,
                actor=request.user,
                target=f'@{profile.nickname}',
                request=request,
            )
            messages.success(request, f'Новий пароль для @{profile.nickname}: {password} — скопіюйте його зараз.')
        elif action == 'create-code':
            temporary_code = TemporaryCode.generate_for(profile.user)
            expires = timezone.localtime(temporary_code.expires_at).strftime('%d.%m.%Y %H:%M')
            log_event(
                AuditEvent.ACTION_CODE_CREATED,
                actor=request.user,
                target=f'@{profile.nickname}',
                detail=f'Діє до {expires}.',
                request=request,
            )
            notice = f'Тимчасовий код для @{profile.nickname}: {temporary_code.code} (діє до {expires}).'
            if request.headers.get('Accept') == 'application/json':
                response = JsonResponse({'code': temporary_code.code, 'message': notice})
                response['Cache-Control'] = 'no-store'
                return response
            messages.success(request, notice)
        else:
            messages.error(request, 'Невідома дія.')
        return redirect('admin-panel')

    query = request.GET.get('q', '').strip()
    profiles = Profile.objects.select_related('user')
    if query:
        profiles = profiles.filter(Q(nickname__icontains=query) | Q(user__username__icontains=query))
    profiles = profiles.order_by('nickname')
    paginator = Paginator(profiles, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    online_since = timezone.now() - ONLINE_WINDOW
    stats = {
        'users': Profile.objects.count(),
        'banned': Profile.objects.filter(is_banned=True).count(),
        'online': Profile.objects.filter(is_banned=False, last_seen__gte=online_since).count(),
        'rooms': Room.objects.count(),
        'posts': Post.objects.count(),
        'comments': Comment.objects.count(),
        'likes': PostLike.objects.count(),
        'chats': Chat.objects.count(),
    }
    recent_events = AuditEvent.objects.select_related('actor').all()[:8]
    return render(
        request,
        'admin.html',
        {
            'profiles': page_obj.object_list,
            'page_obj': page_obj,
            'query': query,
            'stats': stats,
            'role_choices': Profile.ROLE_CHOICES,
            'recent_events': recent_events,
            'app_settings': AppSettings.load(),
        },
    )


@role_required(Profile.ROLE_ANALYST)
def analyst_panel(request):
    now = timezone.now()
    today = timezone.localdate(now)
    start_date = today - timedelta(days=6)
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))

    registrations = (
        User.objects.filter(date_joined__gte=start_dt)
        .annotate(day=TruncDate('date_joined'))
        .values('day')
        .annotate(total=Count('id'))
    )
    posts_per_day = (
        Post.objects.filter(created_at__gte=start_dt)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Count('id'))
    )
    registration_map = {row['day']: row['total'] for row in registrations}
    post_map = {row['day']: row['total'] for row in posts_per_day}
    max_posts = max(post_map.values(), default=0) or 1

    days = []
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        posts_count = post_map.get(day, 0)
        days.append(
            {
                'day': day,
                'label': day.strftime('%d.%m'),
                'posts': posts_count,
                'registrations': registration_map.get(day, 0),
                'height': round(posts_count / max_posts * 100) if posts_count else 0,
            }
        )

    context = {
        'online': Profile.objects.filter(is_banned=False, last_seen__gte=now - ONLINE_WINDOW).count(),
        'users': Profile.objects.count(),
        'active_users': Profile.objects.filter(is_banned=False).count(),
        'rooms': Room.objects.count(),
        'posts': Post.objects.count(),
        'comments': Comment.objects.count(),
        'likes': PostLike.objects.count(),
        'chats': Chat.objects.count(),
        'chat_messages': ChatMessage.objects.count(),
        'days': days,
        'latest_users': User.objects.select_related('profile').order_by('-date_joined')[:6],
        'top_rooms': Room.objects.annotate(
            member_total=Count('members', distinct=True),
            post_total=Count('posts', distinct=True),
        ).order_by('-member_total', '-post_total')[:5],
        'top_users': User.objects.select_related('profile').annotate(
            post_total=Count('posts', distinct=True),
            message_total=Count('chat_messages', distinct=True),
            comment_total=Count('comments', distinct=True),
        ).order_by('-post_total', '-message_total', '-comment_total')[:5],
        'latest_posts': Post.objects.select_related('author', 'room')[:5],
        'events_total': AuditEvent.objects.count(),
        'messages_week': ChatMessage.objects.filter(created_at__gte=start_dt).count(),
        'registrations_week': User.objects.filter(date_joined__gte=start_dt).count(),
    }
    return render(request, 'analyst.html', context)


@role_required(Profile.ROLE_ANALYST)
def analyst_export(request):
    now = timezone.now()
    today = timezone.localdate(now)
    start_date = today - timedelta(days=6)
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))

    registrations = (
        User.objects.filter(date_joined__gte=start_dt)
        .annotate(day=TruncDate('date_joined'))
        .values('day')
        .annotate(total=Count('id'))
    )
    posts_per_day = (
        Post.objects.filter(created_at__gte=start_dt)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Count('id'))
    )
    registration_map = {row['day']: row['total'] for row in registrations}
    post_map = {row['day']: row['total'] for row in posts_per_day}

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="sessionlender-report.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Звіт SessionLender', timezone.localtime(now).strftime('%d.%m.%Y %H:%M')])
    writer.writerow([])
    writer.writerow(['Показник', 'Значення'])
    writer.writerow(['Користувачів', Profile.objects.count()])
    writer.writerow(['Активних', Profile.objects.filter(is_banned=False).count()])
    writer.writerow(['Заблокованих', Profile.objects.filter(is_banned=True).count()])
    writer.writerow(['Онлайн', Profile.objects.filter(is_banned=False, last_seen__gte=now - ONLINE_WINDOW).count()])
    writer.writerow(['Кімнат', Room.objects.count()])
    writer.writerow(['Дописів', Post.objects.count()])
    writer.writerow(['Коментарів', Comment.objects.count()])
    writer.writerow(['Вподобань', PostLike.objects.count()])
    writer.writerow(['Чатів', Chat.objects.count()])
    writer.writerow(['Повідомлень у чатах', ChatMessage.objects.count()])
    writer.writerow([])
    writer.writerow(['Дата', 'Реєстрації', 'Дописи'])
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        writer.writerow(
            [
                day.strftime('%d.%m.%Y'),
                registration_map.get(day, 0),
                post_map.get(day, 0),
            ]
        )
    return response


def error_403(request, exception):
    return render(request, '403.html', status=403)


def error_404(request, exception):
    return render(request, '404.html', status=404)


@login_required
def unread_count_api(request):
    return JsonResponse({'count': ChatMembership.unread_total_for(request.user)})

