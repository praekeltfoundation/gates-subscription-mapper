from django.conf.urls import url

from .views import MigrateSubscriptionListView

urlpatterns = [
    url(
        r'^$', MigrateSubscriptionListView.as_view()),
]
