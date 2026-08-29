import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from ..models import BattleSession, BattleSessionStatus
from .cog import Battle

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.battle")

STALE_SESSION_CUTOFF_MINUTES = 30


async def _refund_stale_sessions():
    """
    A battle escrows its wager once both players are ready. If the bot restarts mid-battle,
    nothing else will ever resolve that session — refund the stake and close it out instead of
    silently stranding the berries.
    """
    cutoff = timezone.now() - timedelta(minutes=STALE_SESSION_CUTOFF_MINUTES)
    stale = [
        s
        async for s in BattleSession.objects.select_related("player1", "player2").filter(
            status__in=(BattleSessionStatus.PROPOSED, BattleSessionStatus.ACTIVE), updated_at__lt=cutoff
        )
    ]
    for session in stale:
        if session.status == BattleSessionStatus.ACTIVE and session.wager_amount:
            await session.player1.add_money(session.wager_amount)
            await session.player2.add_money(session.wager_amount)
            log.info("Refunded stale battle session #%s (%s berries each)", session.pk, session.wager_amount)
        session.status = BattleSessionStatus.CANCELLED
        await session.asave(update_fields=("status",))


async def setup(bot: "BallsDexBot"):
    await _refund_stale_sessions()
    await bot.add_cog(Battle(bot))
