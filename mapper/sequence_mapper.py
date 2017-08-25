# -*- coding: utf-8 -*-
from __future__ import unicode_literals


class SequenceMapper(object):
    """
    Provides the logic for mapping the sequence number from one message set to
    another.
    """
    def map(self, from_messageset, to_messageset, sequence):
        # Default to no mapping
        return sequence


map_sequence = SequenceMapper().map
