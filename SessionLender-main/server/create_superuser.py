import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sessionlender.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.getenv('DJANGO_SUPERUSER_USERNAME')
email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD')

if not username or not password:
    print('Задайте DJANGO_SUPERUSER_USERNAME і DJANGO_SUPERUSER_PASSWORD.')
elif User.objects.filter(username=username).exists():
    print(f'Суперкористувач {username} вже існує.')
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f'Створено суперкористувача {username}.')
