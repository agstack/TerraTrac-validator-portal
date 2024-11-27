# Generated by Django 5.1.3 on 2024-11-27 10:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eudr_backend', '0050_alter_eudrusermodel_user_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eudrusermodel',
            name='user_type',
            field=models.CharField(choices=[('AGENT', 'Agent'), ('ADMIN', 'Admin')], default='AGENT', max_length=255),
        ),
    ]
