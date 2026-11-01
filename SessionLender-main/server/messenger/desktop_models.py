"""A desktop notification key cannot be used to log into the website."""
from django.db import models


class DesktopTicket(models.Model):
    session = models.OneToOneField('sessions.Session', on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()

    class Meta:
        app_label = 'messenger'
