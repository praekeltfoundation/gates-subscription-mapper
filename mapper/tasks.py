from __future__ import absolute_import, unicode_literals
from celery.task import Task
from celery.utils.log import get_task_logger
from django.db import connections, transaction
from django.db.models import F
from django.utils import timezone
from logging import INFO, ERROR
from uuid import uuid4

from .models import LogEvent, MigrateSubscription


class MigrateSubscriptionsTask(Task):
    CHUNK_SIZE = 1000
    logger = get_task_logger(__name__)

    def log(self, migrate, level, message):
        LogEvent.objects.create(
            migrate_subscription=migrate, log_level=level, message=message)
        self.logger.log(level, message)

    def count_identities(self, migrate):
        """
        Counts the number of identities that we need to migrate, and returns
        the value.
        """
        with connections['identities'].cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM {table}'.format(
                    table=migrate.table_name))
            [count] = cursor.fetchone()
        return count

    def generate_identity_query(self, migrate):
        """
        Returns a string which represents the SQL query to fetch all of the
        identities.
        """
        return 'SELECT {column} FROM {table} ORDER BY {column} OFFSET {count}'\
            .format(
                column=migrate.column_name, table=migrate.table_name,
                count=migrate.current)

    def fetch_identities(self, migrate):
        """
        Creates a server side cursor to fetch identities in chunks. Returns
        a generator that yields the identities.
        """
        cursor_name = '_cur_get_identities_{uuid}'.format(uuid=uuid4().hex)
        conn = connections['identities']
        with transaction.atomic(using='identities'), conn.cursor() as cursor:
            cursor.execute(
                'DECLARE {cursor_name} CURSOR for {query}'.format(
                    cursor_name=cursor_name,
                    query=self.generate_identity_query(migrate)
                )
            )
            while True:
                cursor.execute(
                    'FETCH {num} from {cursor}'.format(
                        num=self.CHUNK_SIZE, cursor=cursor_name))
                chunk = cursor.fetchall()
                if not chunk:
                    break
                for row in chunk:
                    yield row[0]

    def migrate_identity(self, migrate, identity):
        """
        Migrates an identity from one messageset to another.
        """
        # TODO: Actually migrate the identity's subscription
        pass

    def run(self, migrate_subscription_id, **kwargs):
        migrate = MigrateSubscription.objects.get(pk=migrate_subscription_id)

        self.log(migrate, INFO, "Setting task ID")
        migrate.task_id = self.request.id
        migrate.status = MigrateSubscription.RUNNING
        migrate.save(update_fields=('task_id', 'status'))
        self.log(
            migrate, INFO,
            "Set task ID to {task_id}".format(task_id=migrate.task_id))

        self.log(migrate, INFO, "Counting identities")
        migrate.total = self.count_identities(migrate)
        migrate.save(update_fields=('total',))
        self.log(
            migrate, INFO,
            "Counted {total} identities".format(total=migrate.total))

        self.log(migrate, INFO, "Processing identities")
        for identity in self.fetch_identities(migrate):
            self.migrate_identity(migrate, identity)
            migrate.current = F('current') + 1
            migrate.save(update_fields=('current',))

        migrate.completed_at = timezone.now()
        migrate.status = MigrateSubscription.COMPLETE
        migrate.save(update_fields=('completed_at', 'status'))
        self.log(
            migrate, INFO,
            "Completed processing identities at {timestamp}".format(
                timestamp=migrate.completed_at))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if 'migrate_subscription_id' in kwargs:
            migrate_subscription_id = kwargs['migrate_subscription_id']
        else:
            migrate_subscription_id = args[0]
        migrate = MigrateSubscription.objects.get(pk=migrate_subscription_id)

        self.log(
            migrate, ERROR, "[{class_name}]: {message}.\n{traceback}".format(
                class_name=exc.__class__.__name__,
                message=str(exc).strip(),
                traceback=str(einfo).strip(),
            ))

        migrate.status = MigrateSubscription.ERROR
        migrate.save(update_fields=('status',))
        return super(MigrateSubscriptionsTask, self).on_failure(
            exc, task_id, args, kwargs, einfo)


migrate_subscriptions = MigrateSubscriptionsTask()
