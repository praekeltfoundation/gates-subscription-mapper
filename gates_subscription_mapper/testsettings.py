from gates_subscription_mapper.settings import * # flake8: noqa

SECRET_KEY = 'REPLACEME'

DEBUG = True

TEMPLATE_DEBUG = True

PASSWORD_HASHERS = ('django.contrib.auth.hashers.MD5PasswordHasher',)

CELERY_TASK_ALWAYS_EAGER = True
