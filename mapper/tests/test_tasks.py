# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.db import connections
from django.conf import settings
from django.test import TestCase
from testfixtures import LogCapture
import json
import responses
import logging
try:
    import mock
except ImportError:
    import unittest.mock as mock

from mapper.models import LogEvent, MigrateSubscription
from mapper.tasks import migrate_subscriptions
from mapper.test_utils import (
    get_calls_to_url, mock_create_subscription, mock_get_subscriptions,
    mock_get_messageset, mock_update_subscription)


class MigrateSubscriptionsTaskTest(TestCase):
    multi_db = True

    def test_log(self):
        """
        The logging function should create a new LogEvent object, as well as
        log the message normally.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        with LogCapture() as l:
            migrate_subscriptions.log(migrate, logging.INFO, 'Test log')

        l.check(
            ('mapper.tasks', 'INFO', 'Test log')
        )
        [log] = LogEvent.objects.all()
        self.assertEqual(log.message, 'Test log')
        self.assertEqual(log.log_level, logging.INFO)
        self.assertEqual(log.migrate_subscription, migrate)

    def test_count_identities(self):
        """
        The count_identities function should return the number of identities
        that we want to migrate.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )

        with connections['identities'].cursor() as cursor:
            # Create the table that we want
            cursor.execute("CREATE TABLE table1 (column1 TEXT)")
            # Create the rows that we want
            for i in range(25):
                cursor.execute("INSERT INTO table1 VALUES (%s)", [str(i)])

        self.assertEqual(migrate_subscriptions.count_identities(migrate), 25)

    def test_fetch_identities(self):
        """
        The fetch_identities function should return all the values of the
        specified field in the specified table.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        with connections['identities'].cursor() as cursor:
            # Create the table that we want
            cursor.execute("CREATE TABLE table1 (column1 INTEGER)")
            # Create the rows that we want
            for i in range(20):
                cursor.execute("INSERT INTO table1 VALUES (%s)", [i])

        migrate_subscriptions.CHUNK_SIZE = 10
        # Queries:
        # 1. Start transaction/savepoint
        # 2. Create cursor
        # 3. Fetch first batch
        # 4. Fetch second batch
        # 5. Fetch third (empty) batch
        # 6. End transaction/savepoint
        with self.assertNumQueries(6, using='identities'):
            identities = sorted(
                migrate_subscriptions.fetch_identities(migrate))
        self.assertEqual(identities, list(range(20)))

    def test_fetch_identities_with_offset(self):
        """
        When we are resuming processing of identities, we want to resume from
        where we left off. If `current` is not 0, we should only return
        the identities that haven't yet been processed
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1', current=10,
        )
        with connections['identities'].cursor() as cursor:
            # Create the table that we want
            cursor.execute("CREATE TABLE table1 (column1 INTEGER)")
            # Create the rows that we want
            for i in range(20):
                cursor.execute("INSERT INTO table1 VALUES (%s)", [i])

        identities = sorted(
            migrate_subscriptions.fetch_identities(migrate))
        self.assertEqual(identities, list(range(10, 20)))

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.migrate_identity')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.fetch_identities')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run(self, count_identities, fetch_identities, migrate_identity):
        """
        Running the task should call the various functions with correct
        parameters.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )

        count_identities.return_value = 2
        fetch_identities.return_value = ['identity1', 'identity2']

        migrate_subscriptions.delay(migrate.pk)

        count_identities.assert_called_once_with(migrate)
        fetch_identities.assert_called_once_with(migrate)
        self.assertEqual(migrate_identity.call_count, 2)
        migrate_identity.assert_any_call(migrate, 'identity1')
        migrate_identity.assert_any_call(migrate, 'identity2')

        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.COMPLETE)
        self.assertNotEqual(migrate.task_id, None)
        self.assertNotEqual(migrate.completed_at, None)
        self.assertEqual(migrate.total, 2)
        self.assertEqual(migrate.current, 2)

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.log')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run_failure_args(self, count_identities, log):
        """
        If the task raises an exception, and the migration object was provided
        in the args, it should create a log object for it and log it, and set
        the status to error.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )

        def error_effect(migrate):
            raise Exception('Test error')
        count_identities.side_effect = error_effect

        migrate_subscriptions.delay(migrate.pk)

        log_args = log.call_args[0]
        self.assertEqual(log_args[0], migrate)
        self.assertEqual(log_args[1], logging.ERROR)
        self.assertTrue('Exception' in log_args[2])
        self.assertTrue('Test error' in log_args[2])
        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.ERROR)

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.log')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run_failure_kwargs(self, count_identities, log):
        """
        If the task raises an exception, and the migration object was provided
        in the kwargs, it should create a log object for it and log it, and set
        the status to error.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )

        def error_effect(migrate):
            raise Exception('Test error')
        count_identities.side_effect = error_effect

        migrate_subscriptions.delay(migrate_subscription_id=migrate.pk)

        log_args = log.call_args[0]
        self.assertEqual(log_args[0], migrate)
        self.assertEqual(log_args[1], logging.ERROR)
        self.assertTrue('Exception' in log_args[2])
        self.assertTrue('Test error' in log_args[2])
        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.ERROR)

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.log')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run_invalid_status(self, count_identities, log):
        """
        If the migration is not in the starting status when the task starts,
        then we should not take any actions.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
            status=MigrateSubscription.CANCELLED)

        migrate_subscriptions.delay(migrate.pk)

        count_identities.assert_not_called()
        log.assert_any_call(migrate, logging.INFO, "Stopping task run")
        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.CANCELLED)

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.migrate_identity')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.fetch_identities')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run_cancelled_midway(
            self, count_identities, fetch_identities, migrate_identities):
        """
        If a migration is cancelled midway, then we should stop running the
        task.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1')

        count_identities.return_value = 2
        fetch_identities.return_value = ['identity1', 'identity2']

        # By setting the side effect of the migrate identity function to
        # cancelling the migration, this will have the effect of cancelling
        # the task when the first identity gets processed.
        def cancel_migration(*args):
            migrate.status = MigrateSubscription.CANCELLED
            migrate.save(update_fields=('status',))
        migrate_identities.side_effect = cancel_migration

        migrate_subscriptions.delay(migrate.pk)

        count_identities.assert_called_once_with(migrate)
        fetch_identities.assert_called_once_with(migrate)
        # Ensure that this is only called once, then the task stopped
        migrate_identities.assert_called_once_with(migrate, 'identity1')

        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.CANCELLED)
        self.assertEqual(migrate.current, 1)
        self.assertEqual(LogEvent.objects.last().message, "Stopping task run")

    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.migrate_identity')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.fetch_identities')
    @mock.patch('mapper.tasks.MigrateSubscriptionsTask.count_identities')
    def test_run_cancelled_after_processing_identities(
            self, count_identities, fetch_identities, migrate_identities):
        """
        If a migration is cancelled after processing all the identities, then
        we should stop running the task.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1')

        count_identities.return_value = 1
        fetch_identities.return_value = ['identity1']

        # By setting the side effect of the migrate identity function to
        # cancelling the migration, this will have the effect of cancelling
        # the task when all the identities have been processed, since we only
        # have one identity
        def cancel_migration(*args):
            migrate.status = MigrateSubscription.CANCELLED
            migrate.save(update_fields=('status',))
        migrate_identities.side_effect = cancel_migration

        migrate_subscriptions.delay(migrate.pk)

        count_identities.assert_called_once_with(migrate)
        fetch_identities.assert_called_once_with(migrate)
        # Ensure that this is only called once, then the task stopped
        migrate_identities.assert_called_once_with(migrate, 'identity1')

        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.CANCELLED)
        self.assertEqual(migrate.current, 1)
        self.assertEqual(LogEvent.objects.last().message, "Stopping task run")

    @responses.activate
    def test_migrate_identity_no_existing_subs(self):
        """
        If an identity doesn't have any existing subscriptions to the specified
        from messageset, then it should be skipped, and the appropriate log
        message should be created.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table', column_name='column')
        mock_get_subscriptions([], '?messageset=1&identity=test-identity')
        # To get the messageset name for the log entry
        mock_get_messageset(1, {'short_name': 'from_messageset'})

        migrate_subscriptions.migrate_identity(migrate, 'test-identity')

        log = LogEvent.objects.last()
        self.assertEqual(log.log_level, logging.ERROR)
        self.assertEqual(
            log.message,
            'Identity test-identity has no existing subscriptions to '
            'from_messageset. Not migrating identity.')

    @responses.activate
    def test_migrate_identity_multiple_subscriptions(self):
        """
        If an identity has multiple subscriptions to the specified from
        messageset, then a warning should be logged, and all of those
        messagesets should be disabled.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table', column_name='column')
        mock_get_subscriptions(
            [{'id': 1, 'next_sequence_number': 1, 'lang': 'afr'},
             {'id': 2, 'next_sequence_number': 2, 'lang': 'eng'}],
            '?messageset=1&identity=test-identity')
        mock_update_subscription(1)
        mock_update_subscription(2)
        # To get the messageset name for the log entry + mapping
        mock_get_messageset(1, {'short_name': 'from_messageset'})
        mock_get_messageset(2, {
            'short_name': 'to_messageset', 'default_schedule': 4})
        mock_create_subscription()

        migrate_subscriptions.migrate_identity(migrate, 'test-identity')

        log = LogEvent.objects.last()
        self.assertEqual(log.log_level, logging.WARNING)
        self.assertEqual(
            log.message, 'Identity test-identity has 2 subscriptions to '
            'from_messageset. All will be cancelled.')

        [cancel_sub1] = list(get_calls_to_url(
            '{url}/subscriptions/{subscription_id}/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, subscription_id=1)))
        self.assertEqual(cancel_sub1.request.method, responses.PATCH)
        self.assertEqual(
            json.loads(cancel_sub1.request.body), {'active': False})

        [cancel_sub2] = list(get_calls_to_url(
            '{url}/subscriptions/{subscription_id}/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, subscription_id=2)))
        self.assertEqual(cancel_sub2.request.method, responses.PATCH)
        self.assertEqual(
            json.loads(cancel_sub2.request.body), {'active': False})

    @responses.activate
    def test_migrate_identity_single_subscription(self):
        """
        If the identity has a single subscription to the from messageset, then
        that should be cancelled, and a new subscription should be created
        for the to messageset.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table', column_name='column')
        mock_get_subscriptions(
            [{'id': 1, 'next_sequence_number': 5, 'lang': 'eng'}],
            '?messageset=1&identity=test-identity')
        mock_update_subscription(1)
        # To get the messageset name for the log entry + mapping
        mock_get_messageset(1, {'short_name': 'from_messageset'})
        mock_get_messageset(2, {
            'short_name': 'to_messageset', 'default_schedule': 4})
        mock_create_subscription()

        migrate_subscriptions.migrate_identity(migrate, 'test-identity')

        self.assertEqual(LogEvent.objects.count(), 0)

        [cancel_sub1] = list(get_calls_to_url(
            '{url}/subscriptions/{subscription_id}/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, subscription_id=1)))
        self.assertEqual(cancel_sub1.request.method, responses.PATCH)
        self.assertEqual(
            json.loads(cancel_sub1.request.body), {'active': False})

        [create_sub] = list(get_calls_to_url(
            '{url}/subscriptions/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, subscription_id=1)))
        self.assertEqual(create_sub.request.method, responses.POST)
        self.assertEqual(json.loads(create_sub.request.body), {
            'identity': 'test-identity',
            'initial_sequence_number': 5,
            'next_sequence_number': 5,
            'lang': 'eng',
            'messageset': 2,
            'schedule': 4,
        })
