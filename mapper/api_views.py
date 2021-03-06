# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ViewSet
from rest_framework import serializers
from seed_services_client.stage_based_messaging import (
    StageBasedMessagingApiClient)
from temba_client.v2 import TembaClient
from uuid import UUID

from mapper.models import MigratedIdentity, RevertedIdentity
from mapper.sequence_mapper import map_backward, NoMappingFound


class RapidproOptoutSerializer(serializers.Serializer):
    contact = serializers.UUIDField()


class InvalidRapidproContact(APIException):
    status_code = HTTP_400_BAD_REQUEST
    default_code = 'invalid_rapidpro_contact'


class RapidproOptout(ViewSet):
    """
    Receives optouts from RapidPro and reverses the migration for the specified
    user.
    """
    authentication_classes = (TokenAuthentication,)
    rapidpro_client = TembaClient(
        settings.RAPIDPRO_URL, settings.RAPIDPRO_TOKEN)
    sbm_client = StageBasedMessagingApiClient(
        settings.STAGE_BASED_MESSAGING_TOKEN,
        settings.STAGE_BASED_MESSAGING_URL)

    def __init__(self, *args, **kwargs):
        self.messagesets = {}
        super(RapidproOptout, self).__init__(*args, **kwargs)

    def get_rapidpro_contact(self, uuid):
        """
        Retrieves the full data for a rapidpro contact, given the UUID.
        """
        contact = self.rapidpro_client.get_contacts(uuid).first()
        if contact is None:
            raise NotFound('Rapidpro contact {} does not exist'.format(uuid))
        return contact

    def find_migration(self, identity_uuid):
        """
        Finds the latest MigrateSubscription for the given identity UUID.
        """
        try:
            migration = MigratedIdentity.objects\
                .filter(identity_uuid=identity_uuid)\
                .select_related('migrate_subscription')\
                .latest('migrate_subscription__created_at')\
                .migrate_subscription
        except MigratedIdentity.DoesNotExist:
            raise InvalidRapidproContact(
                'Seed identity {} does not have any migrations.'.format(
                    identity_uuid))
        return migration

    def get_messageset(self, messageset_id):
        if messageset_id not in self.messagesets:
            self.messagesets[messageset_id] = self.sbm_client.get_messageset(
                messageset_id)
        return self.messagesets[messageset_id]

    def get_messageset_by_shortname(self, short_name):
        return list(self.sbm_client.get_messagesets(
            params={'short_name': short_name})['results'])[0]

    def get_existing_subscriptions(self, identity_uuid):
        """
        Gets all active subscriptions to any gates messagesets for the
        specified identity.
        """
        for sub in self.sbm_client.get_subscriptions({
                'identity': identity_uuid, 'active': True})['results']:
            if 'gates' in self.get_messageset(
                    sub['messageset'])['short_name']:
                yield sub

    def create(self, request):
        """
        Reverses the migration for the specified user.
        """
        serializer = RapidproOptoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contact = self.get_rapidpro_contact(
            serializer.validated_data['contact'])

        try:
            seed_uuid = UUID(contact.fields[settings.RAPIDPRO_UUID_FIELD])
        except (ValueError, TypeError, KeyError):
            raise InvalidRapidproContact(
                'Rapidpro contact {} has an invalid {} field.'.format(
                    contact.uuid, settings.RAPIDPRO_UUID_FIELD))

        migration = self.find_migration(seed_uuid)
        existing_subs = list(self.get_existing_subscriptions(seed_uuid))

        if len(existing_subs) == 0:
            raise InvalidRapidproContact(
                'Seed identity {} has no active subscriptions to '
                'revert'.format(seed_uuid)
            )

        new_subs = []
        for old_sub in existing_subs:
            self.sbm_client.update_subscription(
                old_sub['id'], {'active': False})
            try:
                messageset, sequence = map_backward(
                    self.get_messageset(old_sub['messageset'])['short_name'],
                    old_sub['next_sequence_number']
                )
            except NoMappingFound as e:
                raise InvalidRapidproContact(e.message)
            messageset_id = self.get_messageset_by_shortname(messageset)['id']
            new_subs.append(self.sbm_client.create_subscription({
                'identity': seed_uuid,
                'messageset': messageset_id,
                'initial_sequence_number': sequence,
                'next_sequence_number': sequence,
                'lang': old_sub['lang'],
                'schedule': self.get_messageset(
                    messageset_id)['default_schedule'],
            }))

        RevertedIdentity.objects.create(
            migrate_subscription=migration, identity_uuid=seed_uuid)

        return Response({
            'cancelled_subscriptions': existing_subs,
            'created_subscriptions': new_subs,
        })
