"""
SafeDeal Escrow Bot — Main Entry Point
Run: python main.py
"""

import asyncio
import logging
import nest_asyncio
nest_asyncio.apply()

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from config.settings import settings
from bot.services.db     import db
from bot.services.scheduler import start_scheduler

from bot.handlers.start   import start_handler, help_handler
from bot.handlers.deal    import (
    new_deal_handler, deal_info_handler, my_deals_handler,
    confirm_handler, dispute_handler, auto_release_handler,
    deal_info_callback, delivered_handler,
)
from bot.handlers.wallet  import wallet_handler, connect_wallet_handler
from bot.handlers.channel import (
    channel_setup_handler, channel_settings_handler,
    resolve_dispute_handler, miniapp_handler, webapp_data_handler
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def build_app() -> Application:
    app = Application.builder().token(settings.BOT_TOKEN).build()

    # ── Commands ──────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     start_handler))
    app.add_handler(CommandHandler("help",      help_handler))
    app.add_handler(CommandHandler("newdeal",   new_deal_handler))
    app.add_handler(CommandHandler("mydeals",   my_deals_handler))
    app.add_handler(CommandHandler("deal",      deal_info_handler))
    app.add_handler(CommandHandler("delivered", delivered_handler))
    app.add_handler(CommandHandler("wallet",    wallet_handler))
    app.add_handler(CommandHandler("connect",   connect_wallet_handler))
    app.add_handler(CommandHandler("setup",     channel_setup_handler))
    app.add_handler(CommandHandler("settings",  channel_settings_handler))
    app.add_handler(CommandHandler("app",       miniapp_handler))

    # ── Callbacks ─────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(deal_info_callback,      pattern=r"^dealinfo:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_handler,         pattern=r"^confirm:\d+$"))
    app.add_handler(CallbackQueryHandler(dispute_handler,         pattern=r"^dispute:\d+$"))
    app.add_handler(CallbackQueryHandler(auto_release_handler,    pattern=r"^autorelease:\d+$"))
    app.add_handler(CallbackQueryHandler(resolve_dispute_handler, pattern=r"^resolve:\d+:(seller|buyer|\d+)$"))

    # ── Shortcut callbacks ────────────────────────────────────
    app.add_handler(CallbackQueryHandler(lambda u,c: new_deal_handler(u,c), pattern=r"^goto_newdeal$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: my_deals_handler(u,c), pattern=r"^goto_mydeals$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: wallet_handler(u,c),   pattern=r"^goto_wallet$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: help_handler(u,c),     pattern=r"^goto_help$"))

    # ── Mini App ──────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data_handler))

    return app


async def main():
    await db.init()
    app = build_app()
    await start_scheduler(app)
    logger.info("🔐 SafeDeal Bot starting...")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
