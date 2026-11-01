import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Count, F, Q
from django.utils import timezone


def generate_invite_token():
    return uuid.uuid4().hex


class Profile(models.Model):
    ROLE_USER = 'user'
    ROLE_ADMIN = 'admin'
    ROLE_ANALYST = 'analyst'
    ROLE_CHOICES = [
        (ROLE_USER, 'Користувач'),
        (ROLE_ADMIN, 'Адміністратор'),
        (ROLE_ANALYST, 'Аналітик'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_USER)
    nickname = models.CharField(max_length=40, unique=True)
    bio = models.CharField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    is_banned = models.BooleanField(default=False)
    last_seen = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['nickname']

    def __str__(self):
        return f'@{self.nickname}'

    @classmethod
    def for_user(cls, user):
        cached = getattr(user, '_profile_cache', None)
        if cached is not None:
            return cached
        role = cls.ROLE_ADMIN if user.is_staff or user.is_superuser else cls.ROLE_USER
        profile, _ = cls.objects.get_or_create(
            user=user,
            defaults={'nickname': user.username, 'role': role},
        )
        # Кеш на екземплярі user живе один запит — економить SELECT
        # (middleware + context processor + перевірки ролей).
        setattr(user, '_profile_cache', profile)
        return profile

    @property
    def initials(self):
        return self.nickname[:2].upper()

    @property
    def is_online(self):
        if not self.last_seen:
            return False
        return self.last_seen >= timezone.now() - timedelta(minutes=5)


class AppSettings(models.Model):
    """Єдиний у світі набір глобальних перемикачів спільноти (row pk=1)."""

    allow_user_group_creation = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Налаштування спільноти'
        verbose_name_plural = 'Налаштування спільноти'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Room(models.Model):
    avatar = models.ImageField(upload_to="room_avatars/", blank=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_rooms',
        null=True,
        blank=True,
    )
    members = models.ManyToManyField(User, related_name='rooms')
    invite_token = models.CharField(
        max_length=32,
        unique=True,
        default=generate_invite_token,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_member(self, user):
        return self.members.filter(pk=user.pk).exists()

    def is_owner(self, user):
        return self.created_by_id == user.pk

    def regenerate_invite_token(self):
        self.invite_token = generate_invite_token()
        self.save(update_fields=['invite_token'])
        return self.invite_token


class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='posts')
    image = models.ImageField(upload_to='posts/', blank=True)
    caption = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author.username}: {self.caption[:40]}'


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author.username}: {self.text[:40]}'


class PostLike(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('post', 'user')]
        ordering = ['-created_at']

    def __str__(self):
        return f'@{self.user.username} → {self.post_id}'


class Chat(models.Model):
    KIND_DIRECT = 'direct'
    KIND_GROUP = 'group'
    KIND_CHOICES = [
        (KIND_DIRECT, 'Особистий чат'),
        (KIND_GROUP, 'Груповий чат'),
    ]

    participants_key = models.CharField(max_length=64, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_DIRECT)
    title = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='created_chats',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'Чат {self.participants_key}'

    @property
    def is_group(self):
        return self.kind == self.KIND_GROUP

    @classmethod
    def between(cls, user_a, user_b):
        if user_a.pk == user_b.pk:
            raise ValueError('Не можна створити чат із самим собою.')
        first, second = sorted((user_a, user_b), key=lambda item: item.pk)
        key = f'{first.pk}-{second.pk}'
        with transaction.atomic():
            chat, created = cls.objects.get_or_create(participants_key=key)
            if created:
                ChatMembership.objects.bulk_create(
                    [
                        ChatMembership(chat=chat, user=first, last_read_at=chat.created_at),
                        ChatMembership(chat=chat, user=second, last_read_at=chat.created_at),
                    ]
                )
        return chat, created

    @classmethod
    def create_group(cls, owner, title, users):
        title = (title or '').strip()
        if not title:
            raise ValueError('Назва групи не може бути порожньою.')
        participants = {user.pk: user for user in users if user.pk != owner.pk}
        if not participants:
            raise ValueError('Додайте до групи хоча б одного учасника.')
        with transaction.atomic():
            chat = cls.objects.create(
                participants_key=f'group-{uuid.uuid4().hex}',
                kind=cls.KIND_GROUP,
                title=title,
                created_by=owner,
            )
            ChatMembership.objects.bulk_create(
                [
                    ChatMembership(
                        chat=chat,
                        user=owner,
                        role=ChatMembership.ROLE_OWNER,
                        last_read_at=chat.created_at,
                    ),
                    *[
                        ChatMembership(chat=chat, user=user, last_read_at=chat.created_at)
                        for user in participants.values()
                    ],
                ]
            )
        return chat

    def other_user(self, user):
        for membership in self.memberships.all():
            if membership.user_id != user.pk:
                return membership.user
        return None

    def display_title(self, user=None):
        if self.title:
            return self.title
        if user is not None:
            other = self.other_user(user)
            if other is not None:
                return f'@{other.username}'
        return 'Груповий чат' if self.is_group else 'Особистий чат'

    def display_initials(self, user=None):
        title = self.display_title(user).lstrip('@')
        return title[:2].upper()

    def membership_for(self, user):
        return self.memberships.filter(user=user).first()

    def can_manage(self, user):
        if not self.is_group:
            return False
        membership = self.membership_for(user)
        return bool(membership and membership.role in {ChatMembership.ROLE_OWNER, ChatMembership.ROLE_ADMIN})

    def add_member(self, user, role='member'):
        membership, created = ChatMembership.objects.get_or_create(
            chat=self,
            user=user,
            defaults={'role': role, 'last_read_at': timezone.now()},
        )
        if not created and role != ChatMembership.ROLE_MEMBER:
            membership.role = role
            membership.save(update_fields=['role'])
        return membership, created


class ChatMembership(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Власник'),
        (ROLE_ADMIN, 'Адміністратор'),
        (ROLE_MEMBER, 'Учасник'),
    ]

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [('chat', 'user')]

    def __str__(self):
        return f'@{self.user.username} у {self.chat_id}'

    @property
    def other_user(self):
        for membership in self.chat.memberships.all():
            if membership.user_id != self.user_id:
                return membership.user
        return None

    @property
    def can_manage(self):
        return self.chat.is_group and self.role in {self.ROLE_OWNER, self.ROLE_ADMIN}

    @classmethod
    def unread_total_for(cls, user):
        memberships = cls.objects.filter(user=user).annotate(
            unread=Count(
                'chat__messages',
                filter=Q(chat__messages__created_at__gt=F('last_read_at'))
                & ~Q(chat__messages__author=user),
            )
        )
        return sum(item.unread for item in memberships)


def chat_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()[:12]
    return f'chat/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}'


class ChatMessage(models.Model):
    client_nonce = models.UUIDField(null=True, blank=True, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='replies',
        null=True,
        blank=True,
    )
    text = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['chat', 'created_at'], name='msg_chat_created_idx'),
            models.Index(fields=['author', 'created_at'], name='msg_author_created_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['author', 'chat', 'client_nonce'],
                name='unique_chat_client_nonce',
            )
        ]

    def __str__(self):
        return f'@{self.author.username}: {self.preview[:40]}'

    @property
    def preview(self):
        if self.text:
            return self.text
        attachment = next(iter(self.attachments.all()), None)
        return attachment.label if attachment else 'Повідомлення'

    @property
    def is_edited(self):
        return self.edited_at is not None


class ChatReaction(models.Model):
    ALLOWED_EMOJIS = ('👍', '❤️', '😂', '😮', '😢', '🔥')

    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_reactions')
    emoji = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('message', 'user', 'emoji')]
        ordering = ['created_at']

    def __str__(self):
        return f'{self.emoji} @{self.user.username} → {self.message_id}'


class RoomInvitation(models.Model):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (PENDING, 'Очікує відповіді'),
        (ACCEPTED, 'Прийнято'),
        (REJECTED, 'Відхилено'),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='invitations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_invitations')
    inviter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_room_invitations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_room_invitation')]


class Notification(models.Model):
    KIND_MESSAGE = 'message'
    KIND_MENTION = 'mention'
    KIND_SYSTEM = 'system'
    KIND_CHOICES = [
        (KIND_MESSAGE, 'Нове повідомлення'),
        (KIND_MENTION, 'Згадка'),
        (KIND_SYSTEM, 'Система'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='sent_notifications',
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_MESSAGE)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    invitation = models.OneToOneField(
        RoomInvitation, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notification',
    )
    text = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'], name='messenger_notif_unread_idx'),
            models.Index(fields=['created_at'], name='messenger_notif_created_idx'),
            models.Index(fields=['user', '-created_at'], name='notif_user_created_idx'),
        ]

    def __str__(self):
        return f'@{self.user.username}: {self.text[:40]}'


class ChatAttachment(models.Model):
    KIND_IMAGE = 'image'
    KIND_VOICE = 'voice'
    KIND_FILE = 'file'
    KIND_CHOICES = [
        (KIND_IMAGE, 'Зображення'),
        (KIND_VOICE, 'Голосове повідомлення'),
        (KIND_FILE, 'Файл'),
    ]

    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=chat_upload_to)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_FILE)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.original_name}'

    @property
    def label(self):
        if self.kind == self.KIND_IMAGE:
            return 'Зображення'
        if self.kind == self.KIND_VOICE:
            return 'Голосове повідомлення'
        return self.original_name or 'Файл'

    @property
    def is_image(self):
        return self.kind == self.KIND_IMAGE

    @property
    def is_voice(self):
        return self.kind == self.KIND_VOICE


class TemporaryCode(models.Model):
    code = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='temporary_codes')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} → @{self.user.username}'

    @property
    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()

    @classmethod
    def generate_for(cls, user, hours=24):
        cls.objects.filter(user=user, used=False).update(used=True)
        for _ in range(10):
            code = f'SL-{secrets.token_hex(6).upper()}'
            if not cls.objects.filter(code=code).exists():
                return cls.objects.create(
                    user=user,
                    code=code,
                    expires_at=timezone.now() + timedelta(hours=hours),
                )
        raise RuntimeError('Не вдалося згенерувати унікальний код.')


class AuditEvent(models.Model):
    ACTION_LOGIN_FAILED = 'login-failed'
    ACTION_LOGIN_LOCKED = 'login-locked'
    ACTION_LOGIN_SUCCESS = 'login-success'
    ACTION_REGISTER = 'register'
    ACTION_ROOM_CREATED = 'room-created'
    ACTION_ROOM_DELETED = 'room-deleted'
    ACTION_ROOM_JOINED = 'room-joined'
    ACTION_ROOM_INVITE_RESET = 'room-invite-reset'
    ACTION_POST_DELETED = 'post-deleted'
    ACTION_COMMENT_DELETED = 'comment-deleted'
    ACTION_MESSAGE_DELETED = 'message-deleted'
    ACTION_MESSAGE_EDITED = 'message-edited'
    ACTION_GROUP_CREATED = 'group-created'
    ACTION_GROUP_MEMBER_ADDED = 'group-member-added'
    ACTION_SETTINGS_CHANGED = 'settings-changed'
    ACTION_USER_BANNED = 'user-banned'
    ACTION_USER_UNBANNED = 'user-unbanned'
    ACTION_ROLE_CHANGED = 'role-changed'
    ACTION_PASSWORD_RESET = 'password-reset'
    ACTION_CODE_CREATED = 'code-created'
    ACTION_CHOICES = [
        (ACTION_LOGIN_FAILED, 'Невдалий вхід'),
        (ACTION_LOGIN_LOCKED, 'Вхід заблоковано'),
        (ACTION_LOGIN_SUCCESS, 'Успішний вхід'),
        (ACTION_REGISTER, 'Реєстрація'),
        (ACTION_ROOM_CREATED, 'Створено кімнату'),
        (ACTION_ROOM_DELETED, 'Видалено кімнату'),
        (ACTION_ROOM_JOINED, 'Приєднання до кімнати'),
        (ACTION_ROOM_INVITE_RESET, 'Оновлено запрошення'),
        (ACTION_POST_DELETED, 'Видалено допис'),
        (ACTION_COMMENT_DELETED, 'Видалено коментар'),
        (ACTION_MESSAGE_DELETED, 'Видалено повідомлення'),
        (ACTION_MESSAGE_EDITED, 'Відредаговано повідомлення'),
        (ACTION_GROUP_CREATED, 'Створено групу'),
        (ACTION_GROUP_MEMBER_ADDED, 'Додано учасника групи'),
        (ACTION_SETTINGS_CHANGED, 'Змінено налаштування'),
        (ACTION_USER_BANNED, 'Заблоковано користувача'),
        (ACTION_USER_UNBANNED, 'Розблоковано користувача'),
        (ACTION_ROLE_CHANGED, 'Змінено роль'),
        (ACTION_PASSWORD_RESET, 'Скинуто пароль'),
        (ACTION_CODE_CREATED, 'Створено код доступу'),
    ]

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name='audit_events',
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target = models.CharField(max_length=200, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at'], name='messenger_audit_created_idx')]

    def __str__(self):
        return f'{self.get_action_display()} · {self.target or "—"}'
