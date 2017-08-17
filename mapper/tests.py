# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import connections
from django.conf import settings
from django.contrib.admin.models import LogEntry, ADDITION
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from testfixtures import LogCapture
import json
import responses
import logging
try:
    import mock
except ImportError:
    import unittest.mock as mock

from .models import LogEvent, MigrateSubscription
from .tasks import migrate_subscriptions


class TestBaseTemplate(TestCase):
    # NOTE: We use the login page here as an easy way to test the base template
    def test_logout_link(self):
        """
        If the user is logged in, there should be a logout link.
        """
        response = self.client.get(reverse('login'))
        self.assertNotContains(
            response, '<a href="{}">Logout</a>'.format(reverse('logout')))

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse('login'))
        self.assertContains(
            response, '<a href="{}">Logout</a>'.format(reverse('logout')))

    def test_admin_link(self):
        """
        If the user has access to the django admin, there should be a link
        to the django admin.
        """
        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse('login'))
        self.assertNotContains(
            response, '<a href="{}">Admin</a>'.format(reverse('admin:index')))

        self.client.force_login(User.objects.create_superuser(
            'testadmin', 'testadmin@example.org', 'testpass'))
        response = self.client.get(reverse('login'))
        self.assertContains(
            response, '<a href="{}">Admin</a>'.format(reverse('admin:index')))


def mock_get_messagesets(messagesets):
    responses.add(
        responses.GET,
        '{}/messageset/'.format(settings.STAGE_BASED_MESSAGING_URL),
        json={
            "count": len(messagesets),
            "next": None,
            "previous": None,
            "results": messagesets,
        })


class MigrationSubscriptionsListViewTests(TestCase):
    @responses.activate
    def test_login_required(self):
        """
        To view the list of migrations, you need to be logged in.
        """
        mock_get_messagesets([])
        response = self.client.get(reverse('migration-list'))
        self.assertRedirects(
            response,
            '{}?next={}'.format(reverse('login'), reverse('migration-list'))
        )

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse('migration-list'))
        self.assertEqual(response.status_code, 200)

    @responses.activate
    def test_details_display(self):
        """
        Confirm that the correct details for the migrations are being displayed
        """
        messagesets = {
            1: 'test.messageset.1',
            2: 'test.messageset.2',
        }
        mock_get_messagesets(
            [{'id': k, 'short_name': v} for k, v in messagesets.items()])
        self.client.force_login(User.objects.create_user('testuser'))
        m = MigrateSubscription.objects.create(
            task_id='test-task-id',
            status=MigrateSubscription.RUNNING,
            from_messageset=1,
            to_messageset=2,
            table_name='test-table',
            column_name='test-column',
            total=123,
            current=5,
            completed_at=timezone.now(),
        )

        response = self.client.get(reverse('migration-list'))

        self.assertContains(
            response, '<td>{}</td>'.format(naturaltime(m.created_at)),
            html=True)
        self.assertContains(
            response, '<td>{}</td>'.format(naturaltime(m.completed_at)),
            html=True)
        self.assertContains(
            response, '<td>{} of {}</td>'.format(m.column_name, m.table_name),
            html=True)
        self.assertContains(
            response,
            '<td>{} to {}</td>'.format(
                messagesets[m.from_messageset], messagesets[m.to_messageset]),
            html=True)
        self.assertContains(
            response, '<td>{} {}/{}</td>'.format(
                m.get_status_display(), m.current, m.total),
            html=True)

    @responses.activate
    def test_page_next_and_previous(self):
        """
        If there are next and previous pages, both links should be shown.
        """
        mock_get_messagesets([])
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))
        self.assertNotContains(
            response, '<a href="?page=0">newer</a>', html=True)
        self.assertNotContains(
            response, '<a href="?page=2">older</a>', html=True)

        # Create 3 pages
        for i in range(3 * 20):
            MigrateSubscription.objects.create(
                task_id='test-task-id-{}'.format(i),
                status=MigrateSubscription.RUNNING,
                from_messageset=1,
                to_messageset=2,
                table_name='test-table',
                column_name='test-column',
                total=123,
                current=5,
                completed_at=timezone.now(),
            )

        response = self.client.get(
            '{}?page=2'.format(reverse('migration-list')))

        self.assertContains(
            response, '<a href="?page=1">newer</a>', html=True)
        self.assertContains(
            response, '<a href="?page=3">older</a>', html=True)


class CreateSubscriptionMigrationFormTests(TestCase):
    multi_db = True

    @responses.activate
    def test_form_display_messageset(self):
        """
        Confirm that the correct details for the form messageset selections
        are being displayed.
        """
        messagesets = {
            1: 'test.messageset.1',
            2: 'test.messageset.2',
        }
        mock_get_messagesets(
            [{'id': k, 'short_name': v} for k, v in messagesets.items()])
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))

        messagesets = ''.join([
            '<option value="{}">{}</option>'.format(k, v)
            for k, v in messagesets.items()])
        self.assertContains(
            response,
            '<select name="from_messageset" id="id_from_messageset">'
            '{}</select>'.format(messagesets),
            html=True)
        self.assertContains(
            response,
            '<select name="to_messageset" id="id_to_messageset">'
            '{}</select>'.format(messagesets),
            html=True)

    @responses.activate
    def test_form_display_tables(self):
        """
        Confirm that the correct details for the form table selection is being
        displayed.
        """
        tables = ('testtable1', 'testtable2')
        mock_get_messagesets([])
        with connections['identities'].cursor() as cursor:
            # We first need to remove all existing tables. Django performs
            # migrations on all dbs in tests, and we want a clean DB
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            # Create the tables that we want
            for table in tables:
                cursor.execute("CREATE TABLE {}()".format(table))
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))
        tables = ''.join([
            '<option value="{0}">{0}</option>'.format(t) for t in tables])
        self.assertContains(
            response,
            '<select name="table_name" id="id_table_name">'
            '{}</select>'.format(tables),
            html=True)

    @responses.activate
    def test_form_display_columns(self):
        """
        Confirm that the correct details for the form column selection is being
        displayed.
        """
        tables = {
            'testtable1': ['column1', 'column2'],
            'testtable2': ['column3'],
        }
        mock_get_messagesets([])
        with connections['identities'].cursor() as cursor:
            # We first need to remove all existing tables. Django performs
            # migrations on all dbs in tests, and we want a clean DB
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            # Create the tables that we want
            for table, columns in tables.items():
                columns = ','.join(('{} TEXT'.format(c) for c in columns))
                cursor.execute("CREATE TABLE {}({})".format(table, columns))
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))
        columns = ''.join([
            '<option value="{0}">{0}</option>'.format(c)
            for c in sorted(sum(tables.values(), []))])
        self.assertContains(
            response,
            '<select name="column_name" id="id_column_name">'
            '{}</select>'.format(columns),
            html=True)

    @responses.activate
    def test_form_column_in_table_validation(self):
        """
        If a the selected column is not inside the selected table, then an
        error should be returned.
        """
        tables = {
            'testtable1': ['column1', 'column2'],
            'testtable2': ['column3'],
        }
        messagesets = {
            1: 'test.messageset.1',
            2: 'test.messageset.2',
        }
        mock_get_messagesets(
            [{'id': k, 'short_name': v} for k, v in messagesets.items()])
        with connections['identities'].cursor() as cursor:
            # We first need to remove all existing tables. Django performs
            # migrations on all dbs in tests, and we want a clean DB
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            # Create the tables that we want
            for table, columns in tables.items():
                columns = ','.join(('{} TEXT'.format(c) for c in columns))
                cursor.execute("CREATE TABLE {}({})".format(table, columns))
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.post(reverse('migration-list'), data={
            'table_name': 'testtable1',
            'column_name': tables['testtable2'][0],
            'from_messageset': 1,
            'to_messageset': 2,
        })
        self.assertContains(
            response,
            '<ul class="errorlist"><li>Column {} is not a column in {}'
            '</li></ul>'.format(tables['testtable2'][0], 'testtable1'),
            html=True)

    @responses.activate
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    @mock.patch.object(migrate_subscriptions, 'delay')
    def test_form_correct_submission(self, migrate_subscriptions):
        """
        A correct submission should result in a redirect to the list view,
        a MigrationSubscription creation, and run the relevant celery task.
        """
        tables = {
            'testtable1': ['column1', 'column2'],
            'testtable2': ['column3'],
        }
        messagesets = {
            1: 'test.messageset.1',
            2: 'test.messageset.2',
        }
        mock_get_messagesets(
            [{'id': k, 'short_name': v} for k, v in messagesets.items()])
        with connections['identities'].cursor() as cursor:
            # We first need to remove all existing tables. Django performs
            # migrations on all dbs in tests, and we want a clean DB
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
            # Create the tables that we want
            for table, columns in tables.items():
                columns = ','.join(('{} TEXT'.format(c) for c in columns))
                cursor.execute("CREATE TABLE {}({})".format(table, columns))
        user = User.objects.create_user('testuser')
        self.client.force_login(user)

        response = self.client.post(reverse('migration-list'), data={
            'table_name': 'testtable1',
            'column_name': tables['testtable1'][0],
            'from_messageset': 1,
            'to_messageset': 2,
        })
        self.assertRedirects(response, reverse('migration-list'))

        [migration] = MigrateSubscription.objects.all()
        # Test object is created correctly
        self.assertEqual(migration.table_name, 'testtable1')
        self.assertEqual(migration.column_name, tables['testtable1'][0])
        self.assertEqual(migration.from_messageset, 1)
        self.assertEqual(migration.to_messageset, 2)

        # Test object history is created correctly
        [history] = LogEntry.objects.filter(object_id=migration.pk)
        self.assertEqual(history.user, user)
        self.assertEqual(history.action_flag, ADDITION)
        self.assertEqual(json.loads(history.change_message), [{
            'added': {
                'object': str(migration),
                'name': str(migration._meta.verbose_name),
            }
        }])

        migrate_subscriptions.assert_called_once_with(migration.pk)


class TestLogListView(TestCase):
    def test_login_required(self):
        """
        You need to be logged in to be able to view the list of logs.
        """
        migrate1 = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        url = reverse('log-list', kwargs={'migration_id': migrate1.pk})
        response = self.client.get(url)
        self.assertRedirects(
            response,
            '{}?next={}'.format(reverse('login'), url)
        )

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_view_list_filtered(self):
        """
        Test that only the logs for the selected subscription migration are
        shown.
        """
        migrate1 = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        migrate2 = MigrateSubscription.objects.create(
            from_messageset=3, to_messageset=3,
            table_name='table2', column_name='column2',
        )
        log1 = LogEvent.objects.create(
            migrate_subscription=migrate1, log_level=logging.INFO,
            message="Test log 1")
        log2 = LogEvent.objects.create(
            migrate_subscription=migrate2, log_level=logging.INFO,
            message="Test log 2")

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse(
            'log-list', kwargs={'migration_id': migrate1.pk}))

        self.assertContains(response, log1.message)
        self.assertNotContains(response, log2.message)

    def test_log_display(self):
        """
        Test that the correct information for the logs are shown.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        log = LogEvent.objects.create(
            migrate_subscription=migrate, log_level=logging.INFO,
            message="Test log 1")

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse(
            'log-list', kwargs={'migration_id': migrate.pk}))

        self.assertContains(response, log.get_log_level_display())
        self.assertContains(response, log.message)
        self.assertContains(response, naturaltime(log.created_at))

    def test_page_next_and_previous(self):
        """
        If there are next and previous pages, both links should be shown.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        self.client.force_login(User.objects.create_user('testuser'))
        url = reverse('log-list', kwargs={'migration_id': migrate.pk})
        response = self.client.get(reverse(
            'log-list', kwargs={'migration_id': migrate.pk}))

        self.assertNotContains(
            response, '<a href="?page=0">older</a>', html=True)
        self.assertNotContains(
            response, '<a href="?page=2">newer</a>', html=True)

        # Create 3 pages
        for i in range(3 * 20):
            LogEvent.objects.create(
                migrate_subscription=migrate, log_level=logging.INFO,
                message="Test log {}".format(i))

        response = self.client.get('{}?page=2'.format(url))

        self.assertContains(
            response, '<a href="?page=1">older</a>', html=True)
        self.assertContains(
            response, '<a href="?page=3">newer</a>', html=True)


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
        self.assertEqual(identities, range(20))

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
        self.assertEqual(identities, range(10, 20))

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


class LogEventModelTests(TestCase):
    def test_log_event_display(self):
        """
        Test that the string value of a log event is generate correctly.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        l = LogEvent.objects.create(
            migrate_subscription=migrate, log_level=logging.INFO,
            message='Test log')
        self.assertEqual(str(l), '{} [Info]: Test log'.format(l.created_at))
