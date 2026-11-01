"""Local development only. Vercel loads sessionlender.vercel_asgi directly."""

import os
from pathlib import Path
import secrets

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
from dotenv import load_dotenv


if os.environ.get("SKIP_DOTENV") != "1":
    load_dotenv(BASE / ".env.local")
if os.environ.get("VERCEL") == "1":
    raise RuntimeError("Vercel must use the ASGI entrypoint, not main.py.")
os.environ.setdefault("LOCAL_DEVELOPMENT", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sessionlender.vercel_settings")
if not os.environ.get("DJANGO_SECRET_KEY"):
    key = BASE / ".django-secret"
    if not key.exists():
        with key.open("x") as f:
            f.write(secrets.token_urlsafe(64))
        key.chmod(0o600)
    os.environ["DJANGO_SECRET_KEY"] = key.read_text().strip()

if __name__ == "__main__":
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", interactive=False)
    call_command("collectstatic", interactive=False, verbosity=0)
    import uvicorn

    uvicorn.run(
        "sessionlender.vercel_asgi:application",
        host="127.0.0.1",
        port=int(os.environ.get("SERVER_PORT", os.environ.get("PORT", "8000"))),
        workers=1,
    )
