# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import connections
from django.conf import settings
from django.contrib.admin.models import LogEntry, ADDITION
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
import json
import responses

from .models import MigrateSubscription
from .tasks import test_task


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
    def test_form_correct_submission(self):
        """
        A correct submission should result in a redirect to the list view,
        and an object creation.
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


class TestTaskTest(TestCase):
    def test_test_task(self):
        """
        Ensures that the test task can run.
        """
        test_task.delay()
