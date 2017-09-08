# -*- coding: utf-8 -*-
# Generated by Django 1.11.4 on 2017-08-25 14:43
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mapper', '0004_auto_20170821_1236'),
    ]

    operations = [
        migrations.CreateModel(
            name='MigratedIdentity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identity_uuid', models.UUIDField()),
                ('migrate_subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='identities', to='mapper.MigrateSubscription')),
            ],
        ),
        migrations.AddIndex(
            model_name='migratedidentity',
            index=models.Index(fields=['identity_uuid'], name='mapper_migr_identit_51f479_idx'),
        ),
    ]
