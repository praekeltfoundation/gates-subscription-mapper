# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf import settings
import responses


def mock_get_messagesets(messagesets):
    responses.add(
        responses.GET,
        '{}/messageset/'.format(settings.STAGE_BASED_MESSAGING_URL),
        json={
            "count": len(messagesets),
            "next": None,
            "previous": None,
            "results": messagesets,
        })


def mock_get_messageset(messageset_id, messageset_details):
    responses.add(
        responses.GET,
        '{url}/messageset/{messageset_id}/'.format(
            url=settings.STAGE_BASED_MESSAGING_URL,
            messageset_id=messageset_id),
        json=messageset_details,
    )


def mock_get_subscriptions(subscriptions, querystring=''):
    responses.add(
        responses.GET,
        '{url}/subscriptions/{querystring}'.format(
            url=settings.STAGE_BASED_MESSAGING_URL,
            querystring=querystring),
        json={
            "count": len(subscriptions),
            "next": None,
            "previous": None,
            "results": subscriptions,
        })


def mock_update_subscription(subscription_id):
    responses.add(
        responses.PATCH,
        '{url}/subscriptions/{subscription_id}/'.format(
            url=settings.STAGE_BASED_MESSAGING_URL,
            subscription_id=subscription_id),
        json={}
    )


def mock_create_subscription():
    responses.add(
        responses.POST,
        '{}/subscriptions/'.format(settings.STAGE_BASED_MESSAGING_URL),
        json={}
    )


def get_calls_to_url(url):
    """
    Filters out responses calls to just the ones to the specified url.
    """
    for r in responses.calls:
        if r.request.url == url:
            yield r
