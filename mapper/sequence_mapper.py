# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from math import floor


class NoMappingFound(Exception):
    """
    Raised when we cannot find a mapping for the given messageset and sequence
    number.
    """


class SequenceMapper(object):
    """
    Provides the logic for mapping from one message set to another.
    """
    def map_test_messageset_1(self, sequence):
        """
        Maps from the first testing messageset to the second testing
        messageset.
        """
        return 'test.gates.messageset.2', max(0, 2 * sequence - 1)

    def map_test_messageset_2(self, sequence):
        """
        Maps from the second testing messageset back to the first.
        """
        return 'test.gates.messageset.1', int(floor(sequence / 2.0) + 1)

    def map_forward(self, messageset, sequence):
        """
        Given the short_name of the messageset, and the current sequence number
        returns the tuple (messageset, sequence) of the mapped messageset and
        sequence.
        """
        if messageset == 'test.gates.messageset.1':
            return self.map_test_messageset_1(sequence)
        # If we cannot find any mapping, raise the exception
        raise NoMappingFound(
            "No mapping can be found for messageset {messageset} and sequence "
            "{sequence}".format(messageset=messageset, sequence=sequence))

    def map_backward(self, messageset, sequence):
        """
        Given the short_name of the messageset, and the current sequence number
        returns the tuple (messageset, sequence) of the mapped messageset and
        sequence.
        """
        if messageset == 'test.gates.messageset.2':
            return self.map_test_messageset_2(sequence)
        # If we cannot find any mapping, raise the exception
        raise NoMappingFound(
            "No mapping can be found for messageset {messageset} and sequence "
            "{sequence}".format(messageset=messageset, sequence=sequence))


mapper = SequenceMapper()
map_forward = mapper.map_forward
map_backward = mapper.map_backward
