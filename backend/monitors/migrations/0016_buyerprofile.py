from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('monitors', '0015_heldslot'),
    ]

    operations = [
        migrations.CreateModel(
            name='BuyerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(max_length=30)),
                ('country', models.CharField(default='Italy', max_length=100)),
                ('city', models.CharField(default='Roma', max_length=100)),
                ('birth_date', models.DateField(blank=True, help_text='YYYY-MM-DD', null=True)),
                ('gender', models.CharField(choices=[('M', 'Male'), ('F', 'Female')], default='M', max_length=1)),
                ('language', models.CharField(default='en', max_length=5)),
                ('card_number', models.CharField(blank=True, max_length=20, null=True)),
                ('card_expiry', models.CharField(blank=True, help_text='MM/YYYY', max_length=7, null=True)),
                ('card_cvv', models.CharField(blank=True, max_length=4, null=True)),
                ('card_holder', models.CharField(blank=True, max_length=100, null=True)),
                ('agency', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='buyer_profile', to='monitors.agency')),
            ],
            options={
                'db_table': 'buyer_profiles',
            },
        ),
        migrations.AlterField(
            model_name='monitortask',
            name='tier',
            field=models.CharField(
                choices=[('notify', 'Notify Only'), ('hold', 'Notify + Hold'), ('snipe', 'Notify + Hold + Auto-Pay')],
                default='notify',
                max_length=20,
            ),
        ),
    ]
