# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('issue', '0007_copy_old_data_to_new'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='issue',
            name='documentcontent',
        ),
    ]
