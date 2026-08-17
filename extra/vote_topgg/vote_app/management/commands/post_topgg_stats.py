import asyncio
import json

import aiohttp
from django.core.management.base import BaseCommand, CommandError

from settings.models import load_settings, settings

from ...models import VoteSettings

DISCORD_API = "https://discord.com/api/v10"


async def fetch_guild_count(bot_token: str) -> int:
    """Count the bot's guilds via the REST API, without opening a gateway connection."""
    headers = {"Authorization": f"Bot {bot_token}"}
    count = 0
    after = None

    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            params = {"limit": "200"}
            if after:
                params["after"] = after

            while True:
                async with session.get(f"{DISCORD_API}/users/@me/guilds", params=params) as resp:
                    if resp.status == 429:
                        body = await resp.text()
                        try:
                            retry_after = json.loads(body).get("retry_after", 1.0)
                        except json.JSONDecodeError:
                            retry_after = 1.0
                        await asyncio.sleep(float(retry_after) + 0.1)
                        continue
                    if resp.status != 200:
                        raise CommandError(f"Discord API returned {resp.status}: {await resp.text()}")
                    page = await resp.json()
                    break

            count += len(page)
            if len(page) < 200:
                break
            after = page[-1]["id"]
            await asyncio.sleep(0.5)  # stay comfortably under the rate limit between pages

    return count


async def post_stats() -> None:
    import topgg

    vote_settings = await VoteSettings.aload()

    if not vote_settings.top_gg_stats_token:
        raise CommandError(
            "No Top.gg stats token configured. Set 'top_gg_stats_token' in the Vote settings admin page."
        )
    if not settings.bot_token:
        raise CommandError("No bot token configured in Settings.")

    server_count = await fetch_guild_count(settings.bot_token)

    async with topgg.Client(vote_settings.top_gg_stats_token) as client:
        await client.post_metrics(topgg.Metrics.discord_bot(server_count=server_count))

    print(f"Posted stats to Top.gg: server_count={server_count}")


class Command(BaseCommand):
    help = "Push the current server count to Top.gg, without needing the bot process running."

    def handle(self, *args, **options):
        load_settings()
        asyncio.run(post_stats())
