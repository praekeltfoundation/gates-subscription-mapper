# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms

from .models import MigrateSubscription


class MigrateSubscriptionForm(forms.ModelForm):
    from_messageset = forms.ChoiceField()
    table_name = forms.ChoiceField()
    column_name = forms.ChoiceField()

    def __init__(self, messagesets, db_info, *args, **kwargs):
        super(MigrateSubscriptionForm, self).__init__(*args, **kwargs)
        self.fields['from_messageset'].choices = messagesets

        self.db_info = db_info
        self.fields['table_name'].choices = sorted(
            (n, n) for n in db_info.keys())
        self.fields['column_name'].choices = sorted(set(
            (n, n) for columns in db_info.values() for n in columns))

    def clean_column_name(self):
        """
        Ensure that the column name is a column in the specified table.
        """
        if self.cleaned_data['column_name'] not in self.db_info[
                self.cleaned_data['table_name']]:
            raise forms.ValidationError(
                "Column %(column)s is not a column in %(table)s", params={
                    'column': self.cleaned_data['column_name'],
                    'table': self.cleaned_data['table_name'],
                }, code='invalid')
        return self.cleaned_data['column_name']

    class Meta:
        model = MigrateSubscription
        fields = (
            'from_messageset', 'table_name', 'column_name')
