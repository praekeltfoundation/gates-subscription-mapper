# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-09-06 14:32
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mapper', '0006_auto_20170905_1202'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='migratesubscription',
            name='to_messageset',
        ),
    ]
