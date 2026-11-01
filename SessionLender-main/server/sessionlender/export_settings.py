from .settings import *
DATABASES['default']['NAME'] = os.environ['EXPORT_SQLITE_URI']
DATABASES['default']['OPTIONS'] = {'uri': True}
CHANNEL_LAYERS = {}
