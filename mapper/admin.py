# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms
from django.db import models
from django.contrib import admin

from .models import LogEvent, MigrateSubscription


@admin.register(MigrateSubscription)
class MigrateSubscriptionAdmin(admin.ModelAdmin):
    readonly_fields = (
        'created_at', 'completed_at', 'current', 'total', 'status', 'task_id')
    date_hierarchy = 'created_at'
    list_display = (
        'task_id', 'status', 'table_name', 'column_name', 'current', 'total',
        'created_at')
    formfield_overrides = {
        models.TextField: {'widget': forms.TextInput},
    }


@admin.register(LogEvent)
class LogEventAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    date_hieratchy = 'created_at'
    list_display = ('created_at', 'log_level', 'message')
    formfield_overrides = {
        models.TextField: {'widget': forms.TextInput},
    }
