# Generated by Django 4.0.6 on 2022-08-26 06:51

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('coasc', '0003_rename_account_split_ac_rename_amount_split_am_and_more'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ImpersonalAccount',
            new_name='ImpersonalAc',
        ),
    ]
