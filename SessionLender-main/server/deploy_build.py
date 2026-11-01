"""Build-time DB setup. Never runs migrations for each HTTP invocation."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sessionlender.vercel_settings")
import django

django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction

if os.environ.get("RUN_MIGRATIONS") == "1":
    call_command("migrate", interactive=False)
username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
if username and password:
    with transaction.atomic():
        if not get_user_model().objects.filter(username=username).exists():
            get_user_model().objects.create_superuser(
                username=username,
                password=password,
                email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
            )
            print("Initial administrator created.")
        else:
            print(
                "Administrator bootstrap skipped: account already exists; password unchanged."
            )
print("Vercel build configuration validated. Static assets are collected by Vercel.")
