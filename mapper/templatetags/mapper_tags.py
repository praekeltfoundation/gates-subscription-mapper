# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.template.defaulttags import register


@register.filter
def lookup(dictionary, key):
    return dictionary.get(key)
