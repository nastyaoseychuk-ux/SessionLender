from django.db import migrations


def migrate_existing(apps, schema_editor):
    Friendship = apps.get_model('friendships', 'Friendship')
    Notification = apps.get_model('messenger', 'Notification')
    Profile = apps.get_model('messenger', 'Profile')
    db = schema_editor.connection.alias
    links = list(Friendship.objects.using(db).all())
    pairs = {(link.owner_id, link.friend_id) for link in links}
    names = dict(Profile.objects.using(db).values_list('user_id', 'nickname'))
    for link in links:
        if (link.friend_id, link.owner_id) in pairs:
            link.status = 'accepted'
            link.save(using=db, update_fields=['status'])
        elif not link.notification_id:
            notice = Notification.objects.using(db).create(
                user_id=link.friend_id, actor_id=link.owner_id, kind='system',
                text=f'Користувач @{names.get(link.owner_id, link.owner_id)} хоче з вами дружити',
            )
            link.notification_id = notice.pk
            link.save(using=db, update_fields=['notification'])


class Migration(migrations.Migration):
    dependencies = [('friendships', '0002_friendship_notification_friendship_status')]
    operations = [migrations.RunPython(migrate_existing, migrations.RunPython.noop)]
