# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import connections
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic.edit import ModelFormMixin
from django.views.generic.list import ListView
from seed_services_client.stage_based_messaging import (
    StageBasedMessagingApiClient)

from .forms import MigrateSubscriptionForm
from .models import MigrateSubscription


class MigrateSubscriptionListView(
        LoginRequiredMixin, ListView, ModelFormMixin):
    model = MigrateSubscription
    form_class = MigrateSubscriptionForm
    success_url = reverse_lazy('migration-list')
    paginate_by = 20

    def get_messagesets(self):
        """
        Returns a list of (id, short_name) pairs of all the messagesets.
        The value is cached on the class instance.
        """
        if getattr(self, 'sbm_client', None) is None:
            self.sbm_client = StageBasedMessagingApiClient(
                settings.STAGE_BASED_MESSAGING_TOKEN,
                settings.STAGE_BASED_MESSAGING_URL)
        if getattr(self, 'messagesets', None) is None:
            result = self.sbm_client.get_messagesets()
            self.messagesets = [
                (ms['id'], ms['short_name']) for ms in result['results']]
            self.messagesets.sort(key=lambda ms: ms[1])
        return self.messagesets

    def get_tables(self):
        """
        Returns a sorted list with the names of all the tables in the
        identities database. The value is cached on the class instance.
        """
        if getattr(self, 'table_names', None) is None:
            self.table_names = (
                connections['identities'].introspection.table_names())
        return self.table_names

    def get_table_columns(self, table):
        """
        Returns an sorted list of all the column names in a given table.
        The value is cached on the class instance.
        """
        if getattr(self, 'column_names', None) is None:
            self.column_names = {}
        if self.column_names.get(table) is None:
            cursor = connections['identities'].cursor()
            descrip = connections['identities'].introspection\
                .get_table_description(cursor, table)
            self.column_names[table] = sorted(item.name for item in descrip)
        return self.column_names[table]

    def get_db_info(self):
        """
        Returns a dict where the keys are the table names, and the values are
        sorted lists of all the column names in each table.
        """
        return {
            table: self.get_table_columns(table) for table in self.get_tables()
        }

    # We override the get_form_kwargs function here to add our own choices into
    # the various select fields
    def get_form_kwargs(self):
        kwargs = super(MigrateSubscriptionListView, self).get_form_kwargs()
        kwargs['messagesets'] = self.get_messagesets()
        kwargs['db_info'] = self.get_db_info()
        return kwargs

    def get_context_data(self, *args, **kwargs):
        """
        Add the messageset data to the context.
        """
        return super(MigrateSubscriptionListView, self).get_context_data(
            *args,
            messagesets={k[0]: k[1] for k in self.get_messagesets()},
            **kwargs
        )

    # We have to override the get function here to combine the list and form
    # views, so that we can have both in the same view
    def get(self, request, *args, **kwargs):
        # From ListView
        self.object_list = self.get_queryset()
        # Add the form to the context
        self.object = None
        self.form = self.get_form()
        context = self.get_context_data(
            form=self.form,
        )
        return self.render_to_response(context)

    # We have to override the post function here to add the form validation
    def post(self, request, *args, **kwargs):
        # From ListView
        self.object_list = self.get_queryset()
        # From ProcessFormView
        self.object = None
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
