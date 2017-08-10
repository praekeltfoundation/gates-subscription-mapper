# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import MigrateSubscription


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
    def test_login_required(self):
        """
        To view the list of migrations, you need to be logged in.
        """
        response = self.client.get(reverse('migration-list'))
        self.assertRedirects(
            response,
            '{}?next={}'.format(reverse('login'), reverse('migration-list'))
        )

        self.client.force_login(User.objects.create_user('testuser'))
        response = self.client.get(reverse('migration-list'))
        self.assertEqual(response.status_code, 200)

    def test_details_display(self):
        """
        Confirm that the correct details for the migrations are being displayed
        """
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
            '<td>{} to {}</td>'.format(m.from_messageset, m.to_messageset),
            html=True)
        self.assertContains(
            response, '<td>{} {}/{}</td>'.format(
                m.get_status_display(), m.current, m.total),
            html=True)

    def test_page_next_and_previous(self):
        """
        If there are next and previous pages, both links should be shown.
        """
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
