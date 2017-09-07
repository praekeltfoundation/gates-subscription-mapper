# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from celery.task import Task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.db import connections, transaction
from django.db.models import F
from django.utils import timezone
from logging import INFO, ERROR, WARNING
from seed_services_client.stage_based_messaging import (
    StageBasedMessagingApiClient)
from uuid import uuid4

from mapper.models import LogEvent, MigrateSubscription, MigratedIdentity
from mapper.sequence_mapper import map_forward


class MigrateSubscriptionsTask(Task):
    CHUNK_SIZE = 1000
    logger = get_task_logger(__name__)
    sbm_client = StageBasedMessagingApiClient(
        settings.STAGE_BASED_MESSAGING_TOKEN,
        settings.STAGE_BASED_MESSAGING_URL)

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

    def get_messageset(self, messageset_id):
        if getattr(self, 'messagesets', None) is None:
            self.messagesets = {}
        if messageset_id not in self.messagesets:
            self.messagesets[messageset_id] = self.sbm_client.get_messageset(
                messageset_id)
        return self.messagesets[messageset_id]

    def migrate_identity(self, migrate, identity):
        """
        Migrates an identity from one messageset to another.
        """
        existing_subs = list(self.sbm_client.get_subscriptions({
            'identity': identity,
            'messageset': migrate.from_messageset,
            'active': True,
        })['results'])
        if len(existing_subs) == 0:
            self.log(
                migrate, ERROR,
                "Identity {identity} has no existing subscriptions to {ms}. "
                "Not migrating identity.".format(
                    identity=identity, ms=self.get_messageset(
                        migrate.from_messageset)['short_name'])
            )
            return
        elif len(existing_subs) > 1:
            self.log(
                migrate, WARNING,
                "Identity {identity} has {num} subscriptions to {messageset}. "
                "All will be cancelled.".format(
                    identity=identity, num=len(existing_subs),
                    messageset=self.get_messageset(
                        migrate.from_messageset)['short_name'])
            )

        for sub in existing_subs:
            self.sbm_client.update_subscription(
                sub['id'], data={'active': False})
            (messageset, sequence) = map_forward(
                self.get_messageset(migrate.from_messageset)['short_name'],
                sub['next_sequence_number'],
            )
            messageset_id = self.sbm_client.get_messagesets(
                params={'short_name': messageset})['results'][0]['id']
            self.sbm_client.create_subscription({
                'identity': identity,
                'messageset': messageset_id,
                'initial_sequence_number': sequence,
                'next_sequence_number': sequence,
                'lang': sub['lang'],
                'schedule': self.get_messageset(
                    messageset_id)['default_schedule'],
            })

        MigratedIdentity.objects.create(
            migrate_subscription=migrate, identity_uuid=identity)

    def run(self, migrate_subscription_id, **kwargs):
        migrate = MigrateSubscription.objects.get(pk=migrate_subscription_id)

        self.log(migrate, INFO, "Setting task ID")
        # Atomically transition to running state, stopping the task if it
        # is not in the starting status
        num = MigrateSubscription.objects.filter(
            pk=migrate_subscription_id, status=MigrateSubscription.STARTING
            ).update(
                task_id=self.request.id, status=MigrateSubscription.RUNNING)
        if num != 1:
            self.log(migrate, INFO, "Stopping task run")
            return
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
            # Check to see if the task has been cancelled before each update
            status = MigrateSubscription.objects.values_list(
                'status', flat=True).get(pk=migrate_subscription_id)
            if status != MigrateSubscription.RUNNING:
                self.log(migrate, INFO, "Stopping task run")
                return
            self.migrate_identity(migrate, identity)
            migrate.current = F('current') + 1
            migrate.save(update_fields=('current',))

        # Atomically transision to complete state, stopping the task if it
        # is not in the running status
        num = MigrateSubscription.objects.filter(
            pk=migrate_subscription_id, status=MigrateSubscription.RUNNING
            ).update(
                completed_at=timezone.now(),
                status=MigrateSubscription.COMPLETE)
        if num != 1:
            self.log(migrate, INFO, "Stopping task run")
            return
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
