# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-01-23 21:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('issue', '0021_reprocess_issues'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='issue',
            name='issue_type',
        ),
        migrations.AddField(
            model_name='document',
            name='document_type',
            field=models.IntegerField(choices=[(1, 'Policy'), (2, 'Bylaw'), (3, 'Motion'), (999, 'Other')], default=1),
        ),
    ]
