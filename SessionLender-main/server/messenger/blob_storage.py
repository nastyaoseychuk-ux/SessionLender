"""Django storage for the vercel==0.12.1 synchronous Blob SDK.

Access mode is configurable via the BLOB_ACCESS_MODE setting: 'public' (default,
matches the store created per VERCEL_PUSH.md) or 'private' (requires a Pro plan
and a private-enabled store).
"""

import mimetypes
import posixpath
from functools import lru_cache
from uuid import uuid4

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from vercel.blob import sync as blob
from vercel.blob.errors import BlobNotFoundError


@lru_cache(maxsize=1024)
def metadata(name):
    return blob.head_blob(name)


@deconstructible
class VercelBlobStorage(Storage):
    # За замовчуванням — public: саме такий store створено за VERCEL_PUSH.md.
    # 'private' вимагає Pro-план та store, налаштований на private access.
    access_mode = getattr(django_settings, "BLOB_ACCESS_MODE", "public")

    def get_available_name(self, name, max_length=None):
        folder = posixpath.dirname(name)
        suffix = posixpath.splitext(name)[1].lower()[:10]
        return posixpath.join(folder[:40], uuid4().hex + suffix)

    def _save(self, name, content):
        data = content.read()
        blob.put_blob(
            name,
            data,
            access=self.access_mode,
            content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
        )
        metadata.cache_clear()
        return name

    def _open(self, name, mode="rb"):
        if mode not in ("r", "rb"):
            raise ValueError("Blob storage supports read-only open(). Use save() for writes.")
        try:
            result = blob.get_blob(name, access=self.access_mode)
            return ContentFile(result.body, name=name)
        except Exception:
            try:
                result = blob.get_blob(name, access="public")
                return ContentFile(result.body, name=name)
            except Exception:
                raise

    def url(self, name):
        from django.urls import reverse
        return reverse('private-media', kwargs={'name': name})

    def size(self, name):
        return blob.head_blob(name).size

    def exists(self, name):
        try:
            blob.head_blob(name)
            return True
        except BlobNotFoundError:
            return False
        except Exception:
            return False

    def delete(self, name):
        try:
            blob.delete_blob(name)
        except Exception:
            pass
        metadata.cache_clear()
