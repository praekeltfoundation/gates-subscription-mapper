# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from uuid import uuid4
import responses
import json

from mapper.api_views import RapidproOptout, NotFound, InvalidRapidproContact
from mapper.models import (
    MigrateSubscription, MigratedIdentity, RevertedIdentity)
from mapper.test_utils import (
    mock_get_rapidpro_contacts, mock_get_messageset, mock_get_subscriptions,
    mock_update_subscription, mock_create_subscription, get_calls_to_url)


class TestRapidproOptoutView(TestCase):
    @responses.activate
    def test_get_rapidpro_contact(self):
        """
        Returns the rapidpro contact of the specified uuid.
        """
        uuid = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid), [{
            'uuid': uuid,
            'name': '',
            'language': 'eng',
            'urns': ['tel:+27741234567'],
            'groups': [],
            'fields': {},
            'blocked': False,
            'stopped': False,
            'created_on': '2015-11-11T13:05:57.457742Z',
            'modified_on': '2015-11-11T13:05:57.457742Z',
        }])
        contact = RapidproOptout().get_rapidpro_contact(uuid)
        self.assertEqual(contact.uuid, uuid)

    @responses.activate
    def test_get_rapidpro_contact_no_results(self):
        """
        If there are no results for the specified contact, a NotFound error
        should be raised so that a 404 is returned.
        """
        uuid = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid), [])
        with self.assertRaises(NotFound) as e:
            RapidproOptout().get_rapidpro_contact(uuid)
        self.assertEqual(
            e.exception.detail,
            'Rapidpro contact {uuid} does not exist'.format(uuid=uuid)
        )

    def test_find_migration(self):
        """
        Returns the latest migration for the specified identity.
        """
        identity_uuid = str(uuid4())
        m1 = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column')
        MigratedIdentity.objects.create(
            migrate_subscription=m1, identity_uuid=identity_uuid)
        m2 = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column')
        MigratedIdentity.objects.create(
            migrate_subscription=m2, identity_uuid=identity_uuid)

        m = RapidproOptout().find_migration(identity_uuid)
        self.assertEqual(m, m2)

    def test_find_migration_doesnt_exist(self):
        """
        If no migration exists for the identity, an appropriate error message
        is returned.
        """
        identity_uuid = str(uuid4())

        with self.assertRaises(InvalidRapidproContact) as e:
            RapidproOptout().find_migration(identity_uuid)
        self.assertEqual(
            e.exception.detail,
            'Seed identity {uuid} does not have any migrations.'.format(
                uuid=identity_uuid)
        )

    @responses.activate
    def test_get_messageset(self):
        """
        Returns the details of the messageset specified by the uuid, cached.
        """
        messageset_uuid = str(uuid4())
        messageset = {'foo': 'bar'}
        mock_get_messageset(messageset_uuid, messageset)

        view = RapidproOptout()
        r1 = view.get_messageset(messageset_uuid)
        r2 = view.get_messageset(messageset_uuid)

        self.assertEqual(r1, messageset)
        self.assertEqual(r2, messageset)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_get_existing_subscriptions(self):
        """
        Returns the existing subscriptions to the specified messages for the
        specified identity.
        """
        identity_uuid = str(uuid4())
        subscriptions = [
            {'id': 'sub1'},
            {'id': 'sub2'},
        ]
        mock_get_subscriptions(
            subscriptions, '?identity={uuid}&messageset=1&active=True'.format(
                uuid=identity_uuid))

        subs = RapidproOptout().get_existing_subscriptions(identity_uuid, 1)
        self.assertEqual(subs, subscriptions)

    def test_request_contact_field_required(self):
        """
        The 'contact' field should be required and a valid UUID.
        """
        r = self.client.post(reverse('api:rapidpro-optout-list'), data={})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            json.loads(r.content), {'contact': ['This field is required.']})

        r = self.client.post(reverse('api:rapidpro-optout-list'), data={
            'contact': 'bad-uuid',
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            json.loads(r.content), {
                'contact': ['"bad-uuid" is not a valid UUID.']})

    @responses.activate
    def test_request_contact_identity_uuid_field_invalid(self):
        """
        On the rapidpro contact, if the identity uuid field is missing, or
        an invalid uuid, an error should be returned.
        """
        uuid_missing = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid_missing), [{
            'uuid': uuid_missing,
            'name': '',
            'language': 'eng',
            'urns': ['tel:+27741234567'],
            'groups': [],
            'fields': {},
            'blocked': False,
            'stopped': False,
            'created_on': '2015-11-11T13:05:57.457742Z',
            'modified_on': '2015-11-11T13:05:57.457742Z',
        }])

        r = self.client.post(reverse('api:rapidpro-optout-list'), data={
            'contact': uuid_missing,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            json.loads(r.content), {
                'detail':
                    'Rapidpro contact {uuid} has an invalid {field} field.'
                    .format(
                        uuid=uuid_missing, field=settings.RAPIDPRO_UUID_FIELD)
                })

        uuid_invalid = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid_invalid), [{
            'uuid': uuid_invalid,
            'name': '',
            'language': 'eng',
            'urns': ['tel:+27741234567'],
            'groups': [],
            'fields': {settings.RAPIDPRO_UUID_FIELD: 'bad-uuid'},
            'blocked': False,
            'stopped': False,
            'created_on': '2015-11-11T13:05:57.457742Z',
            'modified_on': '2015-11-11T13:05:57.457742Z',
        }])
        r = self.client.post(reverse('api:rapidpro-optout-list'), data={
            'contact': uuid_invalid,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            json.loads(r.content), {
                'detail':
                    'Rapidpro contact {uuid} has an invalid {field} field.'
                    .format(
                        uuid=uuid_invalid, field=settings.RAPIDPRO_UUID_FIELD)
                })

    @responses.activate
    def test_request_no_active_subscriptions(self):
        """
        For the messageset specified by the latest migration for the identity,
        if the identity doesn't have any active subscriptions to that
        messageset, and error should be returned.
        """
        uuid_identity = str(uuid4())
        uuid_rapidpro = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid_rapidpro), [{
            'uuid': uuid_rapidpro,
            'name': '',
            'language': 'eng',
            'urns': ['tel:+27741234567'],
            'groups': [],
            'fields': {settings.RAPIDPRO_UUID_FIELD: uuid_identity},
            'blocked': False,
            'stopped': False,
            'created_on': '2015-11-11T13:05:57.457742Z',
            'modified_on': '2015-11-11T13:05:57.457742Z',
        }])
        m = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column')
        MigratedIdentity.objects.create(
            migrate_subscription=m, identity_uuid=uuid_identity)
        mock_get_subscriptions(
            [], '?messageset=2&identity={uuid}&active=True'.format(
                uuid=uuid_identity))
        mock_get_messageset(2, {'short_name': 'test.messageset'})

        r = self.client.post(reverse('api:rapidpro-optout-list'), data={
            'contact': uuid_rapidpro,
        })
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            json.loads(r.content), {
                'detail':
                    'Seed identity {uuid} has no active subscriptions to '
                    'test.messageset'.format(uuid=uuid_identity)
                })

    @responses.activate
    def test_request_success(self):
        """
        If all is in order, all existing active subscriptions for the identity
        should be cancelled, and a new subscription should be created. A
        RevertedIdentity object should also be created.
        """
        uuid_identity = str(uuid4())
        uuid_rapidpro = str(uuid4())
        mock_get_rapidpro_contacts('uuid={}'.format(uuid_rapidpro), [{
            'uuid': uuid_rapidpro,
            'name': '',
            'language': 'eng',
            'urns': ['tel:+27741234567'],
            'groups': [],
            'fields': {settings.RAPIDPRO_UUID_FIELD: uuid_identity},
            'blocked': False,
            'stopped': False,
            'created_on': '2015-11-11T13:05:57.457742Z',
            'modified_on': '2015-11-11T13:05:57.457742Z',
        }])
        m = MigrateSubscription.objects.create(
            from_messageset=1, to_messageset=2,
            table_name='test-table', column_name='test-column')
        MigratedIdentity.objects.create(
            migrate_subscription=m, identity_uuid=uuid_identity)
        subscriptions = [
            {'id': 'old-sub-1', 'next_sequence_number': 5, 'lang': 'eng'},
            {'id': 'old-sub-2', 'next_sequence_number': 5, 'lang': 'eng'}]
        mock_get_subscriptions(
            subscriptions,
            '?messageset=2&identity={uuid}&active=True'.format(
                uuid=uuid_identity))
        mock_get_messageset(1, {'short_name': 'test.messageset.1'})
        mock_get_messageset(2, {
            'short_name': 'test.messageset.2',
            'default_schedule': 3,
        })
        mock_update_subscription('old-sub-1')
        mock_update_subscription('old-sub-2')
        mock_create_subscription()

        r = self.client.post(reverse('api:rapidpro-optout-list'), data={
            'contact': uuid_rapidpro,
        })
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(
            json.loads(r.content), {
                'cancelled_subscriptions': subscriptions,
                'created_subscription': {
                    'lang': 'eng',
                    'messageset': 1,
                    'schedule': 3,
                    'next_sequence_number': 5,
                    'initial_sequence_number': 5,
                    'identity': uuid_identity,
                }
            })

        [cancel1] = list(
            get_calls_to_url('{url}/subscriptions/{sub_id}/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, sub_id='old-sub-1')))
        [cancel2] = list(
            get_calls_to_url('{url}/subscriptions/{sub_id}/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL, sub_id='old-sub-2')))
        self.assertEqual(json.loads(cancel1.request.body), {'active': False})
        self.assertEqual(json.loads(cancel2.request.body), {'active': False})

        [create] = list(get_calls_to_url(
            '{url}/subscriptions/'.format(
                url=settings.STAGE_BASED_MESSAGING_URL)))
        self.assertEqual(json.loads(create.request.body), {
            'lang': 'eng',
            'messageset': 1,
            'schedule': 3,
            'initial_sequence_number': 5,
            'next_sequence_number': 5,
            'identity': uuid_identity,
        })

        [reverted] = RevertedIdentity.objects.all()
        self.assertEqual(reverted.migrate_subscription, m)
        self.assertEqual(str(reverted.identity_uuid), uuid_identity)
