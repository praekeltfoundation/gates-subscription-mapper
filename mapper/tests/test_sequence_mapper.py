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

    def test_map_test_messageset_1(self):
        """
        test.messageset.1 should map forward to test.messageset.2 with a scale.
        """
        sequence_from = [0, 1, 2, 3]
        sequence_to = [0, 1, 3, 5]
        for seq_from, seq_to in zip(sequence_from, sequence_to):
            ms, seq = map_forward('test.messageset.1', seq_from)
            self.assertEqual(ms, 'test.messageset.2')
            self.assertEqual(seq, seq_to)

    def test_map_test_messageset_2(self):
        """
        test.messageset.2 should map backwards to test_messageset.1 with a
        scale.
        """
        sequence_from = [1, 2, 3, 4, 5]
        sequence_to = [1, 2, 2, 3, 3]
        for seq_from, seq_to in zip(sequence_from, sequence_to):
            ms, seq = map_backward('test.messageset.2', seq_from)
            self.assertEqual(ms, 'test.messageset.1')
            self.assertEqual(seq, seq_to)
