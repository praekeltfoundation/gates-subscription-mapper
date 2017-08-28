# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.test import TestCase

from mapper.sequence_mapper import map_sequence


class MapSubscriptionsTest(TestCase):
    def test_default_mapping(self):
        """
        By default, the output sequence should equal the input sequence.
        """
        self.assertEqual(map_sequence(None, None, 1), 1)
        self.assertEqual(map_sequence(None, None, 100), 100)
