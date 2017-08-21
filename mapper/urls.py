from django.conf.urls import url

from .views import (
    LogListView, MigrateSubscriptionListView, RetrySubscriptionView,
    CancelSubscriptionView)

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
        CancelSubscriptionView.as_view(), name='migration-cancel')
]
