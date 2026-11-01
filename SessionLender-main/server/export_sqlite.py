"""Read an original SQLite DB without modifying it; upgrade only a temporary copy."""

import argparse
import os
import sqlite3
import tempfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("source", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
source = args.source.resolve()
if not source.is_file():
    p.error("Source database does not exist")
if source == args.output.resolve():
    p.error("Output must not overwrite the source database")
with tempfile.TemporaryDirectory() as directory:
    working = Path(directory) / "export.sqlite3"
    with sqlite3.connect(
        source.as_uri() + "?mode=ro", uri=True
    ) as original, sqlite3.connect(working) as copy:
        original.backup(copy)
    os.environ["DJANGO_SETTINGS_MODULE"] = "sessionlender.export_settings"
    os.environ["EXPORT_SQLITE_URI"] = working.as_uri() + "?mode=rw"
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connections

    try:
        call_command("migrate", interactive=False, verbosity=0)
        call_command(
            "dumpdata",
            natural_foreign=True,
            natural_primary=True,
            indent=2,
            exclude=[
                "contenttypes",
                "auth.permission",
                "sessions.session",
                "admin.logentry",
                "messenger.temporarycode",
            ],
            output=str(args.output),
        )
    finally:
        connections.close_all()
print(
    "Export completed. Original DB unchanged. Keep the JSON private; it contains accounts and messages."
)
