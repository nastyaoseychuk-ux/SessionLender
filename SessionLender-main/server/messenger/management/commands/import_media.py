from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from django.core.files.storage import default_storage
from messenger.models import Profile, Post


class Command(BaseCommand):
    help = 'Upload legacy media to configured Blob storage and update DB references.'
    def add_arguments(self, parser):
        parser.add_argument('directory', type=Path)
    def handle(self, *args, **options):
        root = options['directory'].resolve()
        if not root.is_dir():
            raise CommandError('Media directory does not exist')
        uploaded, missing = 0, 0
        for model, field in ((Profile, 'avatar'), (Post, 'image')):
            for obj in model.objects.exclude(**{field: ''}).iterator():
                old = getattr(obj, field).name
                path = (root / old).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    missing += 1
                    continue
                with path.open('rb') as stream:
                    new = default_storage.save(old, File(stream))
                # No new post/comment event for a storage migration.
                model.objects.filter(pk=obj.pk, **{field: old}).update(**{field: new})
                uploaded += 1
        self.stdout.write(f'Uploaded: {uploaded}; missing/already migrated: {missing}')
