# Generated by Django 5.0.6 on 2024-08-29 12:17

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eudr_backend', '0021_alter_eudrusermodel_user_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='EUDRCollectionSiteModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('site_name', models.CharField(max_length=255)),
                ('site_district', models.CharField(max_length=255)),
                ('site_village', models.CharField(max_length=255)),
                ('site_email', models.EmailField(blank=True, max_length=255, null=True)),
                ('site_phone_number', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AlterField(
            model_name='eudrusermodel',
            name='user_type',
            field=models.CharField(choices=[('AGENT', 'Agent'), ('ADMIN', 'Admin')], default='ADMIN', max_length=255),
        ),
        migrations.AddField(
            model_name='eudrfarmmodel',
            name='site_id',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='eudr_backend.eudrcollectionsitemodel'),
        ),
    ]