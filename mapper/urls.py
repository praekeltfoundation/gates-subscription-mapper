# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf.urls import include, url
from rest_framework.routers import DefaultRouter

from mapper.views import (
    LogListView, MigrateSubscriptionListView, RetrySubscriptionView,
    CancelSubscriptionView)
from mapper.api_views import RapidproOptout

api_router = DefaultRouter()
api_router.register(
    r'rapidpro_optout', RapidproOptout, base_name='rapidpro-optout')

urlpatterns = [
    url(
        r'^$', MigrateSubscriptionListView.as_view(), name='migration-list'),
    url(
        r'^migrations/(?P<migration_id>\d+)/logs/$', LogListView.as_view(),
        name='log-list'),
    url(
        r'^migrations/(?P<migration_id>\d+)/retry/$',
        RetrySubscriptionView.as_view(), name='migration-retry'),
    url(
        r'^migrations/(?P<migration_id>\d+)/cancel/$',
        CancelSubscriptionView.as_view(), name='migration-cancel'),
    url(r'^api/v1/', include(api_router.urls, namespace='api')),
]
