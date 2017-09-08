# -*- coding: utf-8 -*-
from __future__ import unicode_literals


class NoMappingFound(Exception):
    """
    Raised when we cannot find a mapping for the given messageset and sequence
    number.
    """


class SequenceMapper(object):
    """
    Provides the logic for mapping from one message set to another.
    """
    def map_forward(self, messageset, sequence):
        """
        Given the short_name of the messageset, and the current sequence number
        returns the tuple (messageset, sequence) of the mapped messageset and
        sequence.
        """
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
        # If we cannot find any mapping, raise the exception
        raise NoMappingFound(
            "No mapping can be found for messageset {messageset} and sequence "
            "{sequence}".format(messageset=messageset, sequence=sequence))


mapper = SequenceMapper()
map_forward = mapper.map_forward
map_backward = mapper.map_backward
