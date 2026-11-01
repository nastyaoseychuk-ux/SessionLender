from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('messenger', '0007_desktop_ticket')]
    operations = [migrations.AddField(model_name='room', name='avatar',
        field=models.ImageField(blank=True, upload_to='room_avatars/'))]
