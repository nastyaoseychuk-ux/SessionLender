from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction


class Command(BaseCommand):
    help = 'Import a private SQLite export into an empty PostgreSQL application database.'
    def add_arguments(self, parser):
        parser.add_argument('fixture')
    def handle(self, *args, **options):
        if get_user_model().objects.exists():
            raise CommandError('Destination already contains accounts. Import stopped to avoid overwriting data.')
        with transaction.atomic():
            call_command('loaddata', options['fixture'])
        self.stdout.write(self.style.SUCCESS('Accounts and messages imported. Existing password hashes preserved.'))
