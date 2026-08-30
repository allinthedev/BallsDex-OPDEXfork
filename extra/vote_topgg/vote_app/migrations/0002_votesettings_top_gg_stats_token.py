from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vote_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='votesettings',
            name='top_gg_stats_token',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Your bot's API token from Top.gg (Webhooks tab). Used by the "
                "'post_topgg_stats' management command to push the current server count. "
                "Leave empty to skip posting stats.",
                max_length=255,
            ),
        ),
    ]
