# Generated by Django 5.1.3 on 2024-11-26 07:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eudr_backend', '0047_alter_eudrfarmbackupmodel_size_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eudrusermodel',
            name='user_type',
            field=models.CharField(choices=[('AGENT', 'Agent'), ('ADMIN', 'Admin')], default='AGENT', max_length=255),
        ),
    ]
