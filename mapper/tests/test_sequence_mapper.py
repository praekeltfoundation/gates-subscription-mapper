# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.test import TestCase

from mapper.sequence_mapper import map_forward, map_backward, NoMappingFound


class MapSubscriptionsTest(TestCase):
    def test_default_mapping(self):
        """
        By default, an exception should be raised.
        """
        self.assertRaises(NoMappingFound, map_forward, None, None)
        self.assertRaises(NoMappingFound, map_backward, None, None)
