from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .models import Chat, ChatAttachment, ChatMessage, Comment, Post, Profile, Room, TemporaryCode


def clean_nickname_value(value, user=None):
    nickname = value.strip()
    if len(nickname) < 3:
        raise forms.ValidationError('Нікнейм має містити щонайменше 3 символи.')
    if len(nickname) > 30:
        raise forms.ValidationError('Нікнейм не може бути довшим за 30 символів.')
    try:
        User._meta.get_field('username').run_validators(nickname)
    except ValidationError as exc:
        raise forms.ValidationError(exc.messages)
    users = User.objects.filter(username__iexact=nickname)
    profiles = Profile.objects.filter(nickname__iexact=nickname)
    if user is not None:
        users = users.exclude(pk=user.pk)
        profiles = profiles.exclude(user=user)
    if users.exists() or profiles.exists():
        raise forms.ValidationError('Цей нікнейм уже зайнятий.')
    return nickname


class RegisterForm(forms.Form):
    nickname = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'placeholder': 'Нікнейм', 'autocomplete': 'username'}),
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Пароль', 'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Повторіть пароль', 'autocomplete': 'new-password'}),
    )

    def clean_nickname(self):
        return clean_nickname_value(self.cleaned_data['nickname'])

    def clean(self):
        cleaned = super().clean()
        nickname = cleaned.get('nickname')
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Паролі не збігаються.')
        if nickname and password1:
            try:
                validate_password(password1, user=User(username=nickname))
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned

    def save(self):
        with transaction.atomic():
            user = User.objects.create_user(
                username=self.cleaned_data['nickname'],
                password=self.cleaned_data['password1'],
            )
            profile = Profile.objects.get(user=user)
            profile.nickname = self.cleaned_data['nickname']
            profile.save(update_fields=['nickname'])
        return user


class LoginForm(forms.Form):
    nickname = forms.CharField(
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={'placeholder': 'Нікнейм', 'autocomplete': 'username'}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Пароль', 'autocomplete': 'current-password'}),
    )
    code = forms.CharField(
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={'placeholder': 'SL-XXXXXXXXXXXX', 'autocomplete': 'one-time-code'}),
        help_text='Тимчасовий код можна використати замість нікнейма й пароля.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.temporary_code = None

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get('code') or '').strip()
        nickname = (cleaned.get('nickname') or '').strip()
        password = cleaned.get('password') or ''

        if code:
            temporary_code = (
                TemporaryCode.objects.select_related('user')
                .filter(code__iexact=code, used=False, expires_at__gt=timezone.now())
                .first()
            )
            if temporary_code is None:
                self.add_error('code', 'Код недійсний, використаний або прострочений.')
                return cleaned
            profile = Profile.for_user(temporary_code.user)
            if profile.is_banned or not profile.user.is_active:
                self.add_error('code', 'Акаунт заблоковано.')
                return cleaned
            self.temporary_code = temporary_code
            self.user = temporary_code.user
            return cleaned

        if not nickname or not password:
            raise forms.ValidationError('Введіть нікнейм і пароль або тимчасовий код.')

        user = User.objects.filter(username__iexact=nickname).first()
        if user is None:
            profile = Profile.objects.select_related('user').filter(nickname__iexact=nickname).first()
            user = profile.user if profile else None
        if user is None:
            raise forms.ValidationError('Невірний нікнейм або пароль.')

        authenticated = authenticate(username=user.username, password=password)
        if authenticated is None or not authenticated.is_active:
            raise forms.ValidationError('Невірний нікнейм або пароль.')

        profile = Profile.for_user(authenticated)
        if profile.is_banned or not profile.user.is_active:
            raise forms.ValidationError('Акаунт заблоковано адміністратором.')

        self.user = authenticated
        return cleaned


class NicknameForm(forms.Form):
    nickname = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'placeholder': 'Новий нікнейм', 'autocomplete': 'username'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['nickname'].initial = Profile.for_user(user).nickname

    def clean_nickname(self):
        return clean_nickname_value(self.cleaned_data['nickname'], user=self.user)

    def save(self):
        nickname = self.cleaned_data['nickname']
        with transaction.atomic():
            self.user.username = nickname
            self.user.save(update_fields=['username'])
            profile = Profile.for_user(self.user)
            profile.nickname = nickname
            profile.save(update_fields=['nickname'])
        return self.user


class ProfileSettingsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar']
        widgets = {
            'bio': forms.Textarea(
                attrs={
                    'rows': 3,
                    'maxlength': 500,
                    'placeholder': 'Коротко про себе...',
                    'data-autogrow': 'true',
                }
            ),
        }

    def clean_bio(self):
        return self.cleaned_data.get('bio', '').strip()

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and avatar.size > 2 * 1024 * 1024:
            raise forms.ValidationError('Файл завеликий. Максимальний розмір — 2 МБ.')
        return avatar


class RoomForm(forms.ModelForm):
    invitee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True, profile__is_banned=False),
        required=False,
        widget=forms.HiddenInput,
        error_messages={'invalid_choice': 'Цього користувача неможливо додати до кімнати.'},
    )

    class Meta:
        model = Room
        fields = ['name', 'description', 'avatar']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Наприклад, «Робоча кімната»', 'maxlength': 120}),
            'description': forms.TextInput(attrs={'placeholder': 'Короткий опис (необов’язково)', 'maxlength': 255}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Введіть назву кімнати.')
        return name


    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and getattr(avatar, 'size', 0) > 2 * 1024 * 1024:
            raise forms.ValidationError('Файл завеликий. Максимальний розмір — 2 МБ.')
        return avatar


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['room', 'caption', 'image']
        widgets = {
            'caption': forms.Textarea(
                attrs={
                    'rows': 3,
                    'placeholder': 'Поділіться чимось із кімнатою...',
                    'data-autogrow': 'true',
                }
            ),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = user.rooms.all()
        self.fields['room'].empty_label = None
        self.fields['caption'].required = False
        self.fields['image'].required = False

    def clean_caption(self):
        return self.cleaned_data.get('caption', '').strip()

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Файл завеликий. Максимальний розмір — 5 МБ.')
        return image

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('caption') and not cleaned.get('image'):
            raise forms.ValidationError('Додайте підпис або зображення.')
        return cleaned

    def save(self, commit=True):
        post = super().save(commit=False)
        post.author = self.user
        if commit:
            post.save()
        return post


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.TextInput(
                attrs={
                    'placeholder': 'Написати коментар...',
                    'maxlength': 1000,
                    'autocomplete': 'off',
                }
            )
        }

    def clean_text(self):
        text = self.cleaned_data['text'].strip()
        if not text:
            raise forms.ValidationError('Коментар не може бути порожнім.')
        return text


MAX_CHAT_FILE_SIZE = getattr(settings, 'MAX_CHAT_FILE_BYTES', 10 * 1024 * 1024)
MAX_CHAT_TOTAL_SIZE = getattr(settings, 'MAX_CHAT_TOTAL_BYTES', 25 * 1024 * 1024)
MAX_CHAT_ATTACHMENTS = 5
MAX_CHAT_VOICE_SECONDS = 30 * 60
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
ALLOWED_VOICE_TYPES = {
    'audio/webm',
    'audio/ogg',
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/x-wav',
    'audio/mp4',
    'audio/aac',
}
BLOCKED_FILE_EXTENSIONS = {'.html', '.htm', '.svg', '.xml', '.js', '.mjs', '.xhtml'}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]


def normalize_content_type(upload):
    return (getattr(upload, 'content_type', '') or '').split(';')[0].strip().lower()


def safe_upload_name(upload):
    return (Path(upload.name).name or 'file')[:255]


class ChatMessageForm(forms.ModelForm):
    attachments = MultipleFileField(
        required=False,
        label='Файли',
    )
    voice = forms.FileField(
        required=False,
        label='Голосове повідомлення',
    )
    voice_duration = forms.FloatField(
        required=False,
        min_value=0,
        max_value=MAX_CHAT_VOICE_SECONDS,
    )
    reply_to = forms.ModelChoiceField(
        queryset=ChatMessage.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = ChatMessage
        fields = ['text']
        widgets = {
            'text': forms.Textarea(
                attrs={
                    'rows': 2,
                    'maxlength': 2000,
                    'placeholder': 'Напишіть повідомлення...',
                    'data-autogrow': 'true',
                }
            )
        }

    def __init__(self, *args, chat=None, **kwargs):
        self.chat = chat
        super().__init__(*args, **kwargs)
        self.fields['text'].required = False
        self.attachment_specs = []
        if chat is not None:
            self.fields['reply_to'].queryset = chat.messages.select_related('author').all()

    def clean_text(self):
        return (self.cleaned_data.get('text') or '').strip()

    def clean_reply_to(self):
        reply_to = self.cleaned_data.get('reply_to')
        if reply_to and self.chat is not None and reply_to.chat_id != self.chat.pk:
            raise forms.ValidationError('Відповідь має належати цьому чату.')
        return reply_to

    def _validate_upload(self, upload, field_name, forced_kind=None):
        size = getattr(upload, 'size', 0) or 0
        name = safe_upload_name(upload)
        content_type = normalize_content_type(upload)
        if size <= 0:
            self.add_error(field_name, f'Файл «{name}» порожній.')
            return None
        if size > MAX_CHAT_FILE_SIZE:
            limit_mb = max(1, MAX_CHAT_FILE_SIZE // (1024 * 1024))
            self.add_error(field_name, f'Файл «{name}» завеликий. Максимум — {limit_mb} МБ.')
            return None

        if forced_kind == ChatAttachment.KIND_VOICE:
            if not content_type.startswith('audio/'):
                self.add_error(field_name, 'Голосове повідомлення має бути аудіофайлом.')
                return None
            return {
                'upload': upload,
                'kind': ChatAttachment.KIND_VOICE,
                'original_name': name,
                'content_type': content_type,
                'size': size,
            }

        if content_type in ALLOWED_IMAGE_TYPES:
            try:
                Image.open(upload).verify()
            except Image.DecompressionBombError:
                self.add_error(field_name, f'Зображення «{name}» має завелику роздільну здатність.')
                return None
            except (UnidentifiedImageError, OSError):
                self.add_error(field_name, f'Файл «{name}» не є коректним зображенням.')
                return None
            finally:
                upload.seek(0)
            return {
                'upload': upload,
                'kind': ChatAttachment.KIND_IMAGE,
                'original_name': name,
                'content_type': content_type,
                'size': size,
            }

        if content_type.startswith('audio/'):
            if content_type not in ALLOWED_VOICE_TYPES:
                self.add_error(field_name, f'Формат аудіо «{name}» не підтримується.')
                return None
            return {
                'upload': upload,
                'kind': ChatAttachment.KIND_VOICE,
                'original_name': name,
                'content_type': content_type,
                'size': size,
            }

        if Path(name).suffix.lower() in BLOCKED_FILE_EXTENSIONS:
            self.add_error(field_name, f'Файли «{Path(name).suffix}» надсилати заборонено.')
            return None

        return {
            'upload': upload,
            'kind': ChatAttachment.KIND_FILE,
            'original_name': name,
            'content_type': content_type or 'application/octet-stream',
            'size': size,
        }

    def clean(self):
        cleaned = super().clean()
        text = cleaned.get('text') or ''
        uploads = list(cleaned.get('attachments') or [])
        voice = cleaned.get('voice')
        total_uploads = uploads + ([voice] if voice else [])

        if not text and not total_uploads:
            self.add_error('text', 'Додайте текст, файл, зображення або голосове повідомлення.')
            return cleaned
        if len(total_uploads) > MAX_CHAT_ATTACHMENTS:
            self.add_error('attachments', f'За одне повідомлення можна надіслати не більше {MAX_CHAT_ATTACHMENTS} файлів.')
            return cleaned
        if sum(getattr(item, 'size', 0) or 0 for item in total_uploads) > MAX_CHAT_TOTAL_SIZE:
            limit_mb = max(1, MAX_CHAT_TOTAL_SIZE // (1024 * 1024))
            self.add_error('attachments', f'Загальний розмір вкладень перевищує {limit_mb} МБ.')
            return cleaned

        specs = []
        for upload in uploads:
            spec = self._validate_upload(upload, 'attachments')
            if spec:
                specs.append(spec)
        if voice:
            spec = self._validate_upload(voice, 'voice', forced_kind=ChatAttachment.KIND_VOICE)
            if spec:
                spec['duration_seconds'] = cleaned.get('voice_duration')
                specs.append(spec)
        self.attachment_specs = specs
        return cleaned


class ChatMessageEditForm(forms.Form):
    text = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3, 'maxlength': 2000}),
    )

    def __init__(self, *args, message=None, **kwargs):
        self.message = message
        super().__init__(*args, **kwargs)
        if message is not None:
            self.fields['text'].initial = message.text

    def clean_text(self):
        return (self.cleaned_data.get('text') or '').strip()

    def clean(self):
        cleaned = super().clean()
        text = cleaned.get('text') or ''
        if not text and self.message is not None and not self.message.attachments.exists():
            self.add_error('text', 'Повідомлення не може бути порожнім.')
        return cleaned

    def save(self):
        self.message.text = self.cleaned_data['text']
        self.message.edited_at = timezone.now()
        self.message.save(update_fields=['text', 'edited_at'])
        return self.message


class GroupChatForm(forms.Form):
    title = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Назва групи', 'maxlength': 120}),
    )
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        label='Учасники',
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['members'].queryset = (
            User.objects.filter(is_active=True, profile__is_banned=False)
            .exclude(pk=user.pk)
            .select_related('profile')
            .order_by('username')
        )

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if len(title) < 2:
            raise forms.ValidationError('Назва групи має містити щонайменше 2 символи.')
        return title

    def clean_members(self):
        members = self.cleaned_data['members']
        if len(members) > 50:
            raise forms.ValidationError('До групи можна додати не більше 50 учасників.')
        return members

    def save(self):
        return Chat.create_group(
            self.user,
            self.cleaned_data['title'],
            list(self.cleaned_data['members']),
        )


class ChatMemberForm(forms.Form):
    nickname = forms.CharField(
        max_length=40,
        widget=forms.TextInput(attrs={'placeholder': 'Нікнейм учасника', 'autocomplete': 'off'}),
    )

    def __init__(self, chat, *args, **kwargs):
        self.chat = chat
        self.target_user = None
        super().__init__(*args, **kwargs)

    def clean_nickname(self):
        nickname = (self.cleaned_data.get('nickname') or '').strip()
        profile = Profile.objects.select_related('user').filter(nickname__iexact=nickname).first()
        if profile is None:
            raise forms.ValidationError('Користувача з таким нікнеймом не знайдено.')
        if profile.is_banned or not profile.user.is_active:
            raise forms.ValidationError('Цей користувач заблокований.')
        if self.chat.memberships.filter(user=profile.user).exists():
            raise forms.ValidationError('Користувач уже є учасником групи.')
        self.target_user = profile.user
        return nickname

    def save(self):
        membership, _ = self.chat.add_member(self.target_user)
        return membership


class AddMemberForm(forms.Form):
    room = forms.ModelChoiceField(queryset=Room.objects.none(), empty_label=None)
    nickname = forms.CharField(max_length=40)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        self.target_user = None
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = user.created_rooms.all()

    def clean(self):
        cleaned = super().clean()
        nickname = (cleaned.get('nickname') or '').strip()
        room = cleaned.get('room')
        profile = Profile.objects.select_related('user').filter(nickname__iexact=nickname).first()
        if profile is None:
            self.add_error('nickname', 'Користувача з таким нікнеймом не знайдено.')
            return cleaned
        if profile.is_banned or not profile.user.is_active:
            self.add_error('nickname', 'Цей користувач заблокований.')
            return cleaned
        if profile.user_id == self.user.pk:
            self.add_error('nickname', 'Ви вже є учасником власної кімнати.')
            return cleaned
        if room and room.members.filter(pk=profile.user_id).exists():
            self.add_error('nickname', 'Користувач уже є учасником цієї кімнати.')
            return cleaned
        self.target_user = profile.user
        return cleaned

    def save(self):
        from .invitations import invite_to_room

        invite_to_room(self.cleaned_data['room'], self.user, self.target_user)
        return self.target_user
