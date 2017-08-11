# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.list import ListView

from .models import MigrateSubscription


class MigrateSubscriptionListView(LoginRequiredMixin, ListView):
    model = MigrateSubscription
    paginate_by = 20
