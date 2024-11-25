# Generated by Django 5.0.6 on 2024-11-18 08:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eudr_backend', '0046_alter_eudrfarmbackupmodel_coordinates_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eudrfarmbackupmodel',
            name='size',
            field=models.FloatField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='eudrusermodel',
            name='user_type',
            field=models.CharField(choices=[('AGENT', 'Agent'), ('ADMIN', 'Admin')], default='AGENT', max_length=255),
        ),
    ]
