# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms


class MigrateSubscriptionForm(forms.Form):
    from_messageset = forms.ChoiceField()
    to_messageset = forms.ChoiceField()
    table_name = forms.ChoiceField()
    column_name = forms.ChoiceField()

    def __init__(self, messagesets, tables, columns, *args, **kwargs):
        super(MigrateSubscriptionForm, self).__init__(*args, **kwargs)
        self.fields['from_messageset'].choices = messagesets
        self.fields['to_messageset'].choices = messagesets
        self.fields['table_name'].choices = tables
        self.fields['column_name'].choices = columns
