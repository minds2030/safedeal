"""
bot/services/scheduler.py
Background jobs:
1. Auto-release expired deals (every 5 min)
2. Monitor blockchain for new payments (every 1 min)
3. Remind admins of stale disputes (every 1 hour)
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

logger = logging.getLogger(__name__)


async def check_expired_deals(app: Application):
    """Auto-release deals whose guarantee period expired."""
    import time
    from bot.services.db  import db
    from bot.services.evm import evm_service
    from bot.services.ton import ton_service

    now     = int(time.time())
    expired = await db.get_expired_deals(now)
    if not expired:
        return

    logger.info(f"⏱ {len(expired)} expired deals to auto-release")

    for deal in expired:
        try:
            tx = await (ton_service if deal.chain == "ton" else evm_service).auto_release(deal)
            await db.update_deal_status(deal.id, "completed")

            for tg_id in [deal.seller_tg_id, deal.buyer_tg_id]:
                if tg_id:
                    try:
                        await app.bot.send_message(
                            chat_id    = tg_id,
                            text       = (
                                f"⏱ *Deal #{deal.id} Auto-Released*\n\n"
                                f"Guarantee period ended. Funds sent to seller.\n"
                                f"🔗 Tx: `{tx}`"
                            ),
                            parse_mode = "Markdown"
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Auto-release error deal #{deal.id}: {e}")


async def monitor_blockchain(app: Application):
    """Check blockchain for deal status updates."""
    try:
        from bot.services.monitor import monitor_active_deals
        await monitor_active_deals(app)
    except Exception as e:
        logger.error(f"Blockchain monitor error: {e}")


async def remind_stale_disputes(app: Application):
    """Remind admins of disputes open > 24h."""
    from bot.services.db import db

    stale = await db.get_stale_disputes(hours=24)
    for deal in stale:
        channel = await db.get_channel(deal.channel_id)
        if channel and channel.admin_tg_id:
            try:
                await app.bot.send_message(
                    chat_id    = channel.admin_tg_id,
                    text       = (
                        f"🚨 *Reminder: Unresolved Dispute*\n\n"
                        f"Deal #{deal.id} — {deal.description}\n"
                        f"Open for over 24 hours!\n\n"
                        f"Use /deal {deal.id} to resolve."
                    ),
                    parse_mode = "Markdown"
                )
            except Exception:
                pass


async def start_scheduler(app: Application):
    scheduler = AsyncIOScheduler()

    # Auto-release every 5 minutes
    scheduler.add_job(check_expired_deals,  "interval", minutes=5,  args=[app], id="auto_release",       max_instances=1)
    # Monitor blockchain every 60 seconds
    scheduler.add_job(monitor_blockchain,   "interval", seconds=60, args=[app], id="blockchain_monitor", max_instances=1)
    # Dispute reminders every hour
    scheduler.add_job(remind_stale_disputes,"interval", hours=1,    args=[app], id="dispute_reminder",   max_instances=1)

    scheduler.start()
    logger.info("⏰ Scheduler started (auto-release 5min | blockchain monitor 60s | disputes 1h)")
