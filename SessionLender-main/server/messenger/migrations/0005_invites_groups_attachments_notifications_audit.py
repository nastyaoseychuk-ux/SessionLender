import uuid

import messenger.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_invite_tokens(apps, schema_editor):
    Room = apps.get_model('messenger', 'Room')
    for room in Room.objects.filter(invite_token__isnull=True):
        room.invite_token = uuid.uuid4().hex
        room.save(update_fields=['invite_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('messenger', '0004_chatmessage_client_nonce_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='invite_token',
            field=models.CharField(blank=True, editable=False, max_length=32, null=True),
        ),
        migrations.RunPython(populate_invite_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='room',
            name='invite_token',
            field=models.CharField(
                default=messenger.models.generate_invite_token,
                editable=False,
                max_length=32,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='chat',
            name='kind',
            field=models.CharField(
                choices=[('direct', 'Особистий чат'), ('group', 'Груповий чат')],
                default='direct',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='chat',
            name='title',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='chat',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_chats',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='chatmembership',
            name='role',
            field=models.CharField(
                choices=[
                    ('owner', 'Власник'),
                    ('admin', 'Адміністратор'),
                    ('member', 'Учасник'),
                ],
                default='member',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='reply_to',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='replies',
                to='messenger.chatmessage',
            ),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='chatmessage',
            name='text',
            field=models.TextField(blank=True, max_length=2000),
        ),
        migrations.CreateModel(
            name='ChatAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to=messenger.models.chat_upload_to)),
                ('kind', models.CharField(
                    choices=[
                        ('image', 'Зображення'),
                        ('voice', 'Голосове повідомлення'),
                        ('file', 'Файл'),
                    ],
                    default='file',
                    max_length=10,
                )),
                ('original_name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=100)),
                ('size', models.PositiveIntegerField(default=0)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attachments',
                    to='messenger.chatmessage',
                )),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='ChatReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emoji', models.CharField(max_length=8)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reactions',
                    to='messenger.chatmessage',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chat_reactions',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['created_at'],
                'unique_together': {('message', 'user', 'emoji')},
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(
                    choices=[
                        ('message', 'Нове повідомлення'),
                        ('mention', 'Згадка'),
                        ('system', 'Система'),
                    ],
                    default='message',
                    max_length=10,
                )),
                ('text', models.CharField(max_length=255)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sent_notifications',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('chat', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to='messenger.chat',
                )),
                ('message', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to='messenger.chatmessage',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(
                        fields=['user', 'is_read', '-created_at'],
                        name='messenger_notif_unread_idx',
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name='AuditEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(
                    choices=[
                        ('login-failed', 'Невдалий вхід'),
                        ('login-locked', 'Вхід заблоковано'),
                        ('login-success', 'Успішний вхід'),
                        ('register', 'Реєстрація'),
                        ('room-created', 'Створено кімнату'),
                        ('room-deleted', 'Видалено кімнату'),
                        ('room-joined', 'Приєднання до кімнати'),
                        ('room-invite-reset', 'Оновлено запрошення'),
                        ('post-deleted', 'Видалено допис'),
                        ('comment-deleted', 'Видалено коментар'),
                        ('message-deleted', 'Видалено повідомлення'),
                        ('message-edited', 'Відредаговано повідомлення'),
                        ('group-created', 'Створено групу'),
                        ('group-member-added', 'Додано учасника групи'),
                        ('user-banned', 'Заблоковано користувача'),
                        ('user-unbanned', 'Розблоковано користувача'),
                        ('role-changed', 'Змінено роль'),
                        ('password-reset', 'Скинуто пароль'),
                        ('code-created', 'Створено код доступу'),
                    ],
                    max_length=32,
                )),
                ('target', models.CharField(blank=True, max_length=200)),
                ('detail', models.CharField(blank=True, max_length=500)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_events',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(
                        fields=['-created_at'],
                        name='messenger_audit_created_idx',
                    )
                ],
            },
        ),
    ]
