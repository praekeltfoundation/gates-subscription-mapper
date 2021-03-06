# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
import logging


@python_2_unicode_compatible
class MigrateSubscription(models.Model):
    STARTING = 'S'
    RUNNING = 'R'
    CANCELLED = 'D'
    ERROR = 'E'
    COMPLETE = 'C'
    STATUS_CHOICES = (
        (STARTING, 'Starting'),
        (RUNNING, 'Running'),
        (CANCELLED, 'Cancelled'),
        (ERROR, 'Error'),
        (COMPLETE, 'Complete'),
    )

    # The task ID gets filled in when the task starts, to avoid the task
    # trying to load the model before it has been saved.
    task_id = models.TextField(
        "Task ID of the Task", blank=True, null=True, unique=True)
    status = models.CharField(
        "Status of the task", max_length=1, choices=STATUS_CHOICES,
        default=STARTING)
    from_messageset = models.IntegerField(
        "ID of the messageset to transfer subscriptions from")
    table_name = models.TextField("Database table for identity IDs")
    column_name = models.TextField("Column in table for identity IDs")
    # The total number gets filled inside the task, as a count could take
    # a long time.
    total = models.IntegerField(
        "Total number of identities to process", null=True, blank=True)
    current = models.IntegerField(
        "Current count of processed identities", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
        ]

    def can_be_cancelled(self):
        """
        Whether the task is in a state that allows it to be cancelled.
        """
        return self.status == self.STARTING or self.status == self.RUNNING

    def can_be_resumed(self):
        """
        Whether the task is in a state that allows it to be resumed.
        """
        return self.status == self.CANCELLED or self.status == self.ERROR

    def __str__(self):
        return (
            "{status} migrate {column} on {table} from message set {from_ms} "
            "with task {task}"
            .format(
                status=self.get_status_display(), column=self.column_name,
                table=self.table_name, from_ms=self.from_messageset,
                task=self.task_id)
        )


@python_2_unicode_compatible
class LogEvent(models.Model):
    LOG_LEVEL_CHOICES = (
        (logging.CRITICAL, 'Critical'),
        (logging.ERROR, 'Error'),
        (logging.WARNING, 'Warning'),
        (logging.INFO, 'Info'),
        (logging.DEBUG, 'Debug'),
        (logging.NOTSET, 'Not Set'),
    )

    migrate_subscription = models.ForeignKey(
        MigrateSubscription, on_delete=models.CASCADE, related_name='logs')
    log_level = models.IntegerField(
        "Log Level", choices=LOG_LEVEL_CHOICES, default=logging.INFO)
    message = models.TextField("Log Message")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['migrate_subscription', 'created_at'])
        ]

    def __str__(self):
        return "{created_at} [{level}]: {message}".format(
            created_at=self.created_at, level=self.get_log_level_display(),
            message=self.message)


@python_2_unicode_compatible
class MigratedIdentity(models.Model):
    """
    Keeps track of each migrated identity, and on which migration run it was
    migrated on.
    """
    migrate_subscription = models.ForeignKey(
        MigrateSubscription, on_delete=models.CASCADE,
        related_name='migrated_identities')
    identity_uuid = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['identity_uuid'])
        ]
        verbose_name_plural = "migrated identities"

    def __str__(self):
        return "Migrated {identity} on migration run {migrate}".format(
            identity=str(self.identity_uuid),
            migrate=self.migrate_subscription_id)


@python_2_unicode_compatible
class RevertedIdentity(models.Model):
    """
    Keeps track of each identity whose migration was reverted.
    """
    migrate_subscription = models.ForeignKey(
        MigrateSubscription, on_delete=models.CASCADE,
        related_name='reverted_identities')
    identity_uuid = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['identity_uuid'])
        ]
        verbose_name_plural = "reverted identities"

    def __str__(self):
        return "Reverted {identity} from migration run {migrate}".format(
            identity=str(self.identity_uuid),
            migrate=self.migrate_subscription_id)
