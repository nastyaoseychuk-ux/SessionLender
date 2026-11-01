from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('messenger', '0006_room_invitations'),
        ('sessions', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='DesktopTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('session', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='sessions.session')),
            ],
        ),
    ]
