#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    from pathlib import Path
    from dotenv import load_dotenv
    if os.environ.get('SKIP_DOTENV') != '1':
        load_dotenv(Path(__file__).resolve().parent / '.env.local')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sessionlender.vercel_settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
