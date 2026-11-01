"""Bounded notification pages with one message summary per sender."""
from django.db.models import Case, Count, IntegerField, Max, OuterRef, Q, Subquery, Value, When

from .models import Notification

MESSAGE_NOTICE = Q(kind=Notification.KIND_MESSAGE, actor_id__isnull=False, chat_id__isnull=False)


def grouped_notifications(user):
    notices = Notification.objects.filter(user=user)
    messages = notices.filter(MESSAGE_NOTICE).order_by()
    senders = messages.values('actor_id').annotate(latest_id=Max('pk'))
    sender_totals = messages.filter(actor_id=OuterRef('actor_id')).values('actor_id').annotate(
        total=Count('pk'), unread=Count('pk', filter=Q(is_read=False)), chats=Count('chat_id', distinct=True),
    )
    # Filter representatives before slicing; all aggregation stays in the database.
    return notices.filter(~MESSAGE_NOTICE | Q(pk__in=senders.values('latest_id'))).annotate(
        message_count=Case(When(MESSAGE_NOTICE, then=Subquery(sender_totals.values('total')[:1])), default=Value(0), output_field=IntegerField()),
        unread_message_count=Case(When(MESSAGE_NOTICE, then=Subquery(sender_totals.values('unread')[:1])), default=Value(0), output_field=IntegerField()),
        message_chat_count=Case(When(MESSAGE_NOTICE, then=Subquery(sender_totals.values('chats')[:1])), default=Value(0), output_field=IntegerField()),
    ).select_related('actor__profile', 'chat', 'friend_request', 'invitation__room', 'invitation__inviter').order_by('-created_at', '-pk')


def message_word(count):
    if count % 10 == 1 and count % 100 != 11:
        return 'повідомлення'
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return 'повідомлення'
    return 'повідомлень'


def prepare_notice(item):
    if item.message_count:
        nickname = getattr(item.actor.profile, 'nickname', '') or item.actor.username
        item.text = f'Користувач @{nickname}: {item.message_count} {message_word(item.message_count)}'
        item.is_read = item.unread_message_count == 0
    return item
