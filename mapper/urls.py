from django.conf.urls import url

from .views import LogListView, MigrateSubscriptionListView

urlpatterns = [
    url(
        r'^$', MigrateSubscriptionListView.as_view(), name='migration-list'),
    url(
        r'^migrations/(?P<migration_id>\d+)/logs/$', LogListView.as_view(),
        name='log-list'),
]
