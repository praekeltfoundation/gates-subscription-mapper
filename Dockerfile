FROM praekeltfoundation/django-bootstrap:py2

COPY . /app
RUN pip install -e .

ENV DJANGO_SETTINGS_MODULE "gates_subscription_mapper.settings"
ENV CELERY_APP "gates_subscription_mapper"

RUN python manage.py collectstatic --noinput

CMD ["gates_subscription_mapper.wsgi:application"]
