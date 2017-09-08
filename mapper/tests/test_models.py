# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.test import TestCase
import logging

from mapper.models import LogEvent, MigrateSubscription


class LogEventModelTests(TestCase):
    def test_log_event_display(self):
        """
        Test that the string value of a log event is generate correctly.
        """
        migrate = MigrateSubscription.objects.create(
            from_messageset=1,
            table_name='table1', column_name='column1',
        )
        l = LogEvent.objects.create(
            migrate_subscription=migrate, log_level=logging.INFO,
            message='Test log')
        self.assertEqual(str(l), '{} [Info]: Test log'.format(l.created_at))
