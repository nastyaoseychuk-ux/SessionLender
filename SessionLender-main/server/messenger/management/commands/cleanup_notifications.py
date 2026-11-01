from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from messenger.models import Notification


class Command(BaseCommand):
    help = "Delete notifications older than N days"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)
        count, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} notifications"))
