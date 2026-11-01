import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sessionlender.vercel_settings')
from .asgi import application
