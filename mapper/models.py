# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
import logging


@python_2_unicode_compatible
class MigrateSubscription(models.Model):
    STARTING = 'S'
    RUNNING = 'R'
    ERROR = 'E'
    COMPLETE = 'C'
    STATUS_CHOICES = (
        (STARTING, 'Starting'),
        (RUNNING, 'Running'),
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
    to_messageset = models.IntegerField(
        "ID of the messageset to transfer subscriptions to")
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

    def __str__(self):
        return (
            "{status} migrate {column} on {table} from message set {from_ms} "
            "to {to_ms} with task {task}"
            .format(
                status=self.get_status_display(), column=self.column_name,
                table=self.table_name, from_ms=self.from_messageset,
                to_ms=self.to_messageset, task=self.task_id)
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
