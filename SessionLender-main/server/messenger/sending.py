"""Validation, idempotent storage and acknowledgement shared by HTTP and WebSocket."""

import time
import uuid

from django.db import InterfaceError, OperationalError, connections, transaction
from django.urls import reverse
from django.utils import timezone

from .forms import ChatMessageForm
from .models import ChatMembership, ChatMessage, Profile


class SendError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def payload(message, viewer_id):
    # Resolving the image is a separate request, never a Blob API call here.
    read = (
        ChatMembership.objects.filter(chat_id=message.chat_id)
        .exclude(user_id=message.author_id)
        .filter(last_read_at__gte=message.created_at)
        .exists()
    )
    avatar = ""
    if message.author.profile.avatar:
        avatar = reverse("message-avatar", args=[message.author_id])
    return {
        "client_nonce": str(message.client_nonce) if message.client_nonce else None,
        "read": read,
        "id": message.pk,
        "author": message.author.username,
        "initials": message.author.username[:2].upper(),
        "avatar": avatar,
        "text": message.text,
        "time": timezone.localtime(message.created_at).strftime("%H:%M"),
        "created_at": message.created_at.isoformat(),
        "mine": message.author_id == viewer_id,
    }


def validate_text(text):
    if not isinstance(text, str) or len(text) > 2000:
        raise SendError("Повідомлення має містити до 2000 символів.")
    form = ChatMessageForm({"text": text})
    if not form.is_valid():
        errors = [str(error) for values in form.errors.values() for error in values]
        raise SendError(" ".join(errors))
    return form.cleaned_data["text"]


def parse_nonce(nonce):
    if nonce is None:
        return None
    try:
        return uuid.UUID(str(nonce))
    except (ValueError, TypeError, AttributeError):
        raise SendError("Некоректний ідентифікатор повідомлення.")


def require_chat_access(user, chat_id):
    if (
        not user.is_active
        or Profile.objects.filter(user=user, is_banned=True).exists()
        or not ChatMembership.objects.filter(chat_id=chat_id, user=user).exists()
    ):
        raise SendError("Немає доступу до цього чату.", 403)


def save_once(user, chat_id, text, nonce):
    """Return the existing record when the same send attempt is repeated."""
    if not nonce:
        return ChatMessage.objects.create(author=user, chat_id=chat_id, text=text)
    message, _ = ChatMessage.objects.get_or_create(
        author=user, chat_id=chat_id, client_nonce=nonce, defaults={"text": text}
    )
    if message.text != text:
        raise SendError(
            "Цей ідентифікатор уже використаний для іншого повідомлення.", 409
        )
    return message


def store_message(user, chat_id, text, nonce=None):
    # Preserve validation order: type/length, nonce, then form validation.
    if not isinstance(text, str) or len(text) > 2000:
        raise SendError("Повідомлення має містити до 2000 символів.")
    nonce = parse_nonce(nonce)
    text = validate_text(text)
    for attempt in range(2):
        try:
            with transaction.atomic():
                require_chat_access(user, chat_id)
                message = save_once(user, chat_id, text, nonce)
                result = {
                    "type": "sent",
                    "id": message.pk,
                    "client_nonce": str(nonce) if nonce else None,
                    "message": payload(message, user.pk),
                }
            return result
        except (OperationalError, InterfaceError):
            connections.close_all()
            # An ambiguous commit may be retried only with an idempotency key.
            if attempt or nonce is None:
                raise
            time.sleep(0.2)
