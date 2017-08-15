from __future__ import unicode_literals

from .celery import app as celery_app


__version__ = '0.0.1'
VERSION = __version__

__all__ = ['celery_app']
