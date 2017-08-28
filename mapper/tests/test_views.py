# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.db import connections
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import json
import responses
import logging
try:
    import mock
except ImportError:
    import unittest.mock as mock

from mapper.models import LogEvent, MigrateSubscription
from mapper.tasks import migrate_subscriptions
from mapper.test_utils import mock_get_messagesets


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

    @responses.activate
    def test_retry_button(self):
        """
        If a listed migration is in the error or cancelled state, then there
        should be a retry button.
        """
        m = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column',
        )
        mock_get_messagesets([])
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))
        self.assertNotContains(
            response, '<button type="submit">Retry</button>', html=True)

        m.status = MigrateSubscription.ERROR
        m.save()
        response = self.client.get(reverse('migration-list'))
        self.assertContains(
            response, '<button type="submit">Retry</button>', html=True)

        m.status = MigrateSubscription.CANCELLED
        m.save()
        response = self.client.get(reverse('migration-list'))
        self.assertContains(
            response, '<button type="submit">Retry</button>', html=True)

    @responses.activate
    def test_cancel_button(self):
        """
        If a listed migration can be cancelled, then there should be a cancel
        button.
        """
        m = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column',
            status=MigrateSubscription.ERROR)
        mock_get_messagesets([])
        self.client.force_login(User.objects.create_user('testuser'))

        response = self.client.get(reverse('migration-list'))
        self.assertNotContains(
            response, '<button type="submit">Cancel</button>', html=True)

        m.status = MigrateSubscription.STARTING
        m.save()
        response = self.client.get(reverse('migration-list'))
        self.assertContains(
            response, '<button type="submit">Cancel</button>', html=True)

        m.status = MigrateSubscription.RUNNING
        m.save()
        response = self.client.get(reverse('migration-list'))
        self.assertContains(
            response, '<button type="submit">Cancel</button>', html=True)


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


class TestRetrySubscriptionMigrate(TestCase):
    def test_login_required(self):
        """
        You must be logged in to be able to use this endpoint.
        """
        url = reverse('migration-retry', kwargs={'migration_id': 1})
        response = self.client.post(url)
        self.assertRedirects(
            response,
            '{}?next={}'.format(reverse('login'), url)
        )

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_missing_migration(self):
        """
        If the migration specified by the id doesn't exist, a 404 should be
        returned.
        """
        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(
            reverse('migration-retry', kwargs={'migration_id': 1}))
        self.assertEqual(response.status_code, 404)

    def test_non_error_migration(self):
        """
        If a migration is not in error status, then we cannot retry it, so
        a bad request error should be returned.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
        )
        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(
            reverse('migration-retry', kwargs={'migration_id': migrate.pk}))
        self.assertEqual(response.status_code, 400)

    @mock.patch('mapper.tasks.migrate_subscriptions.delay')
    @responses.activate
    def test_successful_retry(self, migrate_subscriptions):
        """
        On a valid request, the migration status should be set to starting,
        the retry action should be logged on the history, a new log object
        should be created, and the celery task should be started.
        """
        mock_get_messagesets([])
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
            status=MigrateSubscription.ERROR,
        )
        user = User.objects.create_user('testuser')
        self.client.force_login(user)
        response = self.client.post(
            reverse('migration-retry', kwargs={'migration_id': migrate.pk}))
        self.assertRedirects(response, reverse('migration-list'))

        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.STARTING)

        history = LogEntry.objects.last()
        self.assertEqual(history.user, user)
        self.assertEqual(history.action_flag, CHANGE)
        self.assertEqual(history.change_message, "Retried task")

        log = LogEvent.objects.last()
        self.assertEqual(log.migrate_subscription, migrate)
        self.assertEqual(log.log_level, logging.INFO)
        self.assertEqual(log.message, "Retrying task")

        migrate_subscriptions.assert_called_once_with(migrate.pk)


class TestCancelSubscriptionMigrate(TestCase):
    def test_login_required(self):
        """
        You must be logged in to be able to use this endpoint.
        """
        url = reverse('migration-cancel', kwargs={'migration_id': 1})
        response = self.client.post(url)
        self.assertRedirects(
            response,
            '{}?next={}'.format(reverse('login'), url)
        )

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_missing_migration(self):
        """
        If the migration specified by the id doesn't exist, a 404 should be
        returned.
        """
        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(
            reverse('migration-cancel', kwargs={'migration_id': 1}))
        self.assertEqual(response.status_code, 404)

    def test_non_running_migration(self):
        """
        If a migration is not in starting or running status, then we cannot
        cancel it, so a bad request error should be returned.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
            status=MigrateSubscription.ERROR,
        )
        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.post(
            reverse('migration-cancel', kwargs={'migration_id': migrate.pk}))
        self.assertEqual(response.status_code, 400)

    @responses.activate
    def test_successful_cancel(self):
        """
        On a valid request, the migration status should be set to cancelled,
        the cancel action should be logged on the history, and a new log object
        should be created.
        """
        mock_get_messagesets([])
        migrate = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='table1', column_name='column1',
            status=MigrateSubscription.RUNNING,
        )
        user = User.objects.create_user('testuser')
        self.client.force_login(user)
        response = self.client.post(
            reverse('migration-cancel', kwargs={'migration_id': migrate.pk}))
        self.assertRedirects(response, reverse('migration-list'))

        migrate.refresh_from_db()
        self.assertEqual(migrate.status, MigrateSubscription.CANCELLED)

        history = LogEntry.objects.last()
        self.assertEqual(history.user, user)
        self.assertEqual(history.action_flag, CHANGE)
        self.assertEqual(history.change_message, "Cancelled task")

        log = LogEvent.objects.last()
        self.assertEqual(log.migrate_subscription, migrate)
        self.assertEqual(log.log_level, logging.INFO)
        self.assertEqual(log.message, "Cancelling task")
