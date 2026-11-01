from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import timezone
from .models import (
    ChatMembership,
    ChatMessage,
    Comment,
    Notification,
    Post,
    PostLike,
    Profile,
    Room,
    RoomInvitation,
)
from django.db.models import F
from .sending import store_message, SendError, payload
from django.db import OperationalError, InterfaceError
from .delivery import relay
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils.crypto import constant_time_compare


def chat_group_name(chat_id):
    return f'chat_{chat_id}'


def broadcast_chat(chat_id, event_type, **payload):
    relay([(chat_group_name(chat_id), {'type': event_type, **payload})])


def broadcast_message_created(message):
    broadcast_chat(message.chat_id, 'chat.message', id=message.pk)


def broadcast_message_updated(message):
    broadcast_chat(
        message.chat_id,
        'chat.message.updated',
        message=serialize_message(message),
    )


def broadcast_message_deleted(chat_id, message_id):
    broadcast_chat(chat_id, 'chat.message.deleted', message_id=message_id)


def broadcast_reactions(chat_id, message):
    broadcast_chat(
        chat_id,
        'chat.reaction.updated',
        message_id=message.pk,
        reactions=serialize_reactions(message),
    )


def broadcast_read(chat_id, user_id, last_read_at):
    broadcast_chat(
        chat_id,
        'chat.read',
        user_id=user_id,
        last_read=last_read_at.isoformat() if last_read_at else None,
    )


def serialize_reactions(message, user=None):
    groups = {}
    for reaction in message.reactions.all():
        groups.setdefault(reaction.emoji, []).append(reaction.user_id)
    return [
        {
            'emoji': emoji,
            'count': len(user_ids),
            'users': user_ids,
            'mine': bool(user and user.pk in user_ids),
        }
        for emoji, user_ids in groups.items()
    ]


def serialize_message(message, user=None, other_last_read=None):
    profile = getattr(message.author, 'profile', None)
    attachments = [
        {
            'id': attachment.pk,
            'kind': attachment.kind,
            'name': attachment.original_name,
            'url': reverse('chat-attachment', args=[attachment.pk]),
            'size': attachment.size,
            'size_display': filesizeformat(attachment.size),
            'duration': attachment.duration_seconds,
        }
        for attachment in message.attachments.all()
    ]
    reply = None
    if message.reply_to_id:
        reply_message = message.reply_to
        reply = {
            'id': reply_message.pk,
            'author': reply_message.author.username,
            'text': reply_message.preview,
            'mine': bool(user and reply_message.author_id == user.pk),
        }
    mine = bool(user and message.author_id == user.pk)
    read = bool(mine and other_last_read and message.created_at <= other_last_read)
    avatar = (
        reverse('message-avatar', args=[message.author_id])
        if profile and profile.avatar
        else ''
    )
    return {
        'id': message.pk,
        'chat_id': message.chat_id,
        'author_id': message.author_id,
        'author': message.author.username,
        'initials': profile.initials if profile else message.author.username[:2].upper(),
        'avatar': avatar,
        'text': message.text,
        'preview': message.preview,
        'attachments': attachments,
        'reply': reply,
        'reactions': serialize_reactions(message, user),
        'time': timezone.localtime(message.created_at).strftime('%H:%M'),
        'created_at': message.created_at.isoformat(),
        'edited': message.is_edited,
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'mine': mine,
        'read': read,
    }


def notify_chat_message(message):
    text = f'@{message.author.username}: {message.preview}'[:255]
    recipients = (
        ChatMembership.objects.filter(chat=message.chat)
        .exclude(user_id=message.author_id)
        .values_list('user_id', flat=True)
    )
    Notification.objects.bulk_create(
        [
            Notification(
                user_id=user_id,
                actor=message.author,
                kind=Notification.KIND_MESSAGE,
                chat=message.chat,
                message=message,
                text=text,
            )
            for user_id in recipients
        ]
    )


def mark_chat_notifications_read(chat_id, user):
    Notification.objects.filter(
        user=user,
        chat_id=chat_id,
        is_read=False,
    ).update(is_read=True)


def message_for_broadcast(message):
    return (
        ChatMessage.objects.select_related(
            'author', 'author__profile', 'reply_to__author'
        )
        .prefetch_related('attachments', 'reactions')
        .get(pk=message.pk)
    )


def session_valid(scope):
    user = scope["user"]
    if not user.is_authenticated:
        return False
    fresh = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    return bool(
        fresh
        and Session.objects.filter(
            session_key=scope["session"].session_key, expire_date__gt=timezone.now()
        ).exists()
        and constant_time_compare(
            fresh.get_session_auth_hash(), scope["session"].get("_auth_user_hash", "")
        )
    )


class ChatConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def permitted(self):
        user = self.scope["user"]
        return (
            session_valid(self.scope)
            and not Profile.objects.filter(user=user, is_banned=True).exists()
            and ChatMembership.objects.filter(chat_id=self.chat_id, user=user).exists()
        )

    async def connect(self):
        self.chat_id = int(self.scope["url_route"]["kwargs"]["chat_id"])
        self.group = f"chat_{self.chat_id}"
        self.joined = False
        if not await self.permitted():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group, self.channel_name)
        self.joined = True
        await self.accept()
        await self.send_json(
            {"type": "ready", "read_through": await self.read_through()}
        )

    async def disconnect(self, code):
        if getattr(self, "joined", False):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    @database_sync_to_async
    def read_through(self):
        membership = (
            ChatMembership.objects.filter(chat_id=self.chat_id)
            .exclude(user=self.scope["user"])
            .first()
        )
        return membership.last_read_at.isoformat() if membership else None

    @database_sync_to_async
    def messages(self, after):
        items = (
            ChatMessage.objects.filter(chat_id=self.chat_id, pk__gt=after)
            .select_related("author__profile")
            .order_by("pk")[:200]
        )
        result = []
        for m in items:
            result.append(payload(m, self.scope["user"].pk))
        return result

    @database_sync_to_async
    def mark_read(self, message_id):
        message = ChatMessage.objects.filter(
            chat_id=self.chat_id, pk=message_id
        ).first()
        if not message:
            return
        updated = ChatMembership.objects.filter(
            chat_id=self.chat_id,
            user=self.scope["user"],
            last_read_at__lt=message.created_at,
        ).update(last_read_at=message.created_at)
        if updated:
            relay(
                [
                    (
                        self.group,
                        {
                            "type": "chat.read",
                            "user_id": self.scope["user"].pk,
                            "through": message.created_at.isoformat(),
                        },
                    ),
                    (f'user_{self.scope["user"].pk}', {"type": "inbox.changed"}),
                ]
            )

    async def chat_read(self, event):
        if await self.permitted():
            through = event.get("through") or event.get("last_read")
            await self.send_json(
                {
                    "type": "read",
                    "user_id": event["user_id"],
                    "through": through,
                }
            )

    @database_sync_to_async
    def save_message(self, text, nonce=None):
        from django.conf import settings
        from .security import is_rate_limited_identity

        if not getattr(settings, 'TEST', False):
            if is_rate_limited_identity(
                f'ws:{self.scope["user"].pk}',
                'chat_message',
                getattr(settings, 'MESSAGE_RATE_LIMIT', 30),
                getattr(settings, 'MESSAGE_RATE_WINDOW', 60),
            ):
                return {
                    'type': 'error',
                    'message': 'Забагато повідомлень. Спробуйте пізніше.',
                    'client_nonce': nonce,
                }
        try:
            return store_message(self.scope["user"], self.chat_id, text, nonce)
        except SendError as error:
            return {"type": "error", "message": str(error), "client_nonce": nonce}
        except (OperationalError, InterfaceError):
            return {"type": "retry", "client_nonce": nonce}

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict) or content.get("type") not in (
            "sync",
            "send",
            "read",
        ):
            return
        if not await self.permitted():
            await self.close(code=4403)
            return
        handlers = {
            "read": self.receive_read,
            "send": self.receive_send,
            "sync": self.receive_sync,
        }
        await handlers[content["type"]](content)

    async def receive_read(self, content):
        try:
            await self.mark_read(int(content.get("id", 0)))
        except (ValueError, TypeError):
            pass

    async def receive_send(self, content):
        text = content.get("text")
        if not isinstance(text, str) or len(text) > 2000:
            await self.send_json(
                {
                    "type": "error",
                    "message": "Повідомлення має містити до 2000 символів.",
                }
            )
            return
        await self.send_json(await self.save_message(text, content.get("client_nonce")))

    async def receive_sync(self, content):
        try:
            after = max(0, int(content.get("after", 0)))
        except (ValueError, TypeError):
            await self.close(code=4400)
            return
        items = await self.messages(after)
        await self.send_json(
            {
                "type": "messages",
                "messages": items,
                "sync": True,
                "more": len(items) == 200,
                "after": items[-1]["id"] if items else after,
            }
        )

    async def chat_message(self, event):
        # A user must remain authorized after connection, including bans/removals.
        if not await self.permitted():
            await self.close(code=4403)
            return
        if 'message' in event:
            await self.send_json({'type': 'message', 'message': event['message']})
            return
        items = await self.messages(event["id"] - 1)
        await self.send_json({"type": "messages", "messages": items})

    async def chat_message_updated(self, event):
        if await self.permitted():
            await self.send_json(
                {'type': 'message.updated', 'message': event['message']}
            )

    async def chat_message_deleted(self, event):
        if await self.permitted():
            await self.send_json(
                {'type': 'message.deleted', 'message_id': event['message_id']}
            )

    async def chat_reaction_updated(self, event):
        if await self.permitted():
            await self.send_json(
                {
                    'type': 'reaction.updated',
                    'message_id': event['message_id'],
                    'reactions': event['reactions'],
                }
            )


class InboxConsumer(AsyncJsonWebsocketConsumer):
    @database_sync_to_async
    def unread(self):
        user = self.scope["user"]
        if (
            not session_valid(self.scope)
            or Profile.objects.filter(user=user, is_banned=True).exists()
        ):
            return None
        return ChatMembership.unread_total_for(user)

    async def connect(self):
        self.joined = False
        if await self.unread() is None:
            await self.close(code=4403)
            return
        self.group = f'user_{self.scope["user"].pk}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        self.joined = True
        await self.accept()
        await self.inbox_changed({})
        for message_id in await self.missed_messages():
            await self.server_notice({"kind": "message", "id": message_id})

    async def disconnect(self, code):
        if self.joined:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def inbox_changed(self, event):
        count = await self.unread()
        if count is None:
            await self.close(code=4403)
            return
        await self.send_json({"type": "unread", "count": count})

    @database_sync_to_async
    def missed_messages(self):
        return list(
            ChatMessage.objects.filter(
                chat__memberships__user=self.scope["user"],
                created_at__gt=F("chat__memberships__last_read_at"),
            )
            .exclude(author=self.scope["user"])
            .order_by("-pk")
            .values_list("pk", flat=True)[:20]
        )[::-1]

    @database_sync_to_async
    def notification(self, event):
        user = self.scope["user"]
        if (
            not session_valid(self.scope)
            or Profile.objects.filter(user=user, is_banned=True).exists()
        ):
            return None
        kind = event.get("kind")
        pk = event.get("id")
        notice_id = f"{kind}:{pk}"
        if kind == "message":
            details = self.message_notice(user, pk)
        elif kind == "post":
            details = self.post_notice(user, pk)
        elif kind in ("comment", "like"):
            details = self.reaction_notice(user, pk, kind)
        elif kind == "room":
            details = self.room_notice(user, pk)
        elif kind == "friend_request":
            from friendships.models import Friendship
            link = Friendship.objects.filter(pk=pk, friend=user, status=Friendship.PENDING, owner__profile__is_banned=False).select_related('owner__profile').first()
            if link is None:
                return None
            details = ('Запит на дружбу', f'Користувач @{link.owner.profile.nickname} хоче з вами дружити', '/friends/?filter=requests')
        elif kind == "room_invitation":
            invitation = RoomInvitation.objects.filter(
                pk=pk, user=user, status=RoomInvitation.PENDING,
            ).select_related('room', 'inviter').first()
            if invitation is None:
                return None
            notice_id += ':' + invitation.created_at.isoformat()
            name = f'@{invitation.inviter.username}' if invitation.inviter else 'Користувач'
            details = ('Запрошення до кімнати', f'Вас запросив {name} до кімнати {invitation.room.name}', '/messages/notifications/')
        else:
            return None
        if details is None:
            return None
        title, body, path = details
        return {
            "type": "notification",
            "id": notice_id,
            "title": title,
            "body": body,
            "path": path,
            **self.notification_identity(kind, pk),
        }

    def notification_identity(self, kind, pk):
        from django.contrib.auth.models import User
        from friendships.models import Friendship
        actor_id = None
        if kind == 'message':
            actor_id = ChatMessage.objects.filter(pk=pk).values_list('author_id', flat=True).first()
        elif kind == 'post':
            actor_id = Post.objects.filter(pk=pk).values_list('author_id', flat=True).first()
        elif kind == 'comment':
            actor_id = Comment.objects.filter(pk=pk).values_list('author_id', flat=True).first()
        elif kind == 'like':
            actor_id = PostLike.objects.filter(pk=pk).values_list('user_id', flat=True).first()
        elif kind == 'room':
            actor_id = Room.objects.filter(pk=pk).values_list('created_by_id', flat=True).first()
        elif kind == 'room_invitation':
            actor_id = RoomInvitation.objects.filter(pk=pk).values_list('inviter_id', flat=True).first()
        elif kind == 'friend_request':
            actor_id = Friendship.objects.filter(pk=pk).values_list('owner_id', flat=True).first()
        actor = User.objects.select_related('profile').filter(pk=actor_id).first()
        if not actor:
            return {}
        profile = getattr(actor, 'profile', None)
        return {'nickname': '@' + (profile.nickname if profile else actor.username),
                'avatar': reverse('desktop-avatar', args=[actor.pk]) if profile and profile.avatar else ''}

    def message_notice(self, user, pk):
        obj = (
            ChatMessage.objects.filter(pk=pk, chat__memberships__user=user)
            .exclude(author=user)
            .select_related("author")
            .first()
        )
        if not obj:
            return None
        title, body, path = (
            f"Повідомлення від @{obj.author.username}",
            obj.preview[:200],
            f"/messages/{obj.chat_id}/",
        )
        return title, body, path

    def post_notice(self, user, pk):
        obj = (
            Post.objects.filter(pk=pk, room__members=user)
            .exclude(author=user)
            .select_related("room", "author")
            .first()
        )
        if not obj:
            return None
        title, body, path = (
            f"Новий допис: {obj.room.name}",
            f"@{obj.author.username}: {obj.caption[:150]}",
            f"/rooms/{obj.room_id}/",
        )
        return title, body, path

    def reaction_notice(self, user, pk, kind):
        model = Comment if kind == "comment" else PostLike
        obj = (
            model.objects.filter(pk=pk, post__author=user, post__room__members=user)
            .select_related("post", "author" if kind == "comment" else "user")
            .first()
        )
        if not obj:
            return None
        actor = obj.author if kind == "comment" else obj.user
        if actor.pk == user.pk:
            return None
        title = (
            "Коментар до вашого допису"
            if kind == "comment"
            else "Вподобання вашого допису"
        )
        body = (
            f"@{actor.username}: {obj.text[:150]}"
            if kind == "comment"
            else f"@{actor.username} вподобав(-ла) ваш допис"
        )
        path = f"/rooms/{obj.post.room_id}/"
        return title, body, path

    def room_notice(self, user, pk):
        obj = Room.objects.filter(pk=pk, members=user).first()
        if not obj:
            return None
        title, body, path = "Вас додано до кімнати", obj.name, f"/rooms/{obj.pk}/"
        return title, body, path

    async def server_notice(self, event):
        notice = await self.notification(event)
        if notice:
            await self.send_json(notice)
