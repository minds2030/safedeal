"""
bot/services/monitor.py
Blockchain monitor — watches for incoming payments to the contract
Runs every 60 seconds, updates deal status automatically
"""

import asyncio
import logging
from web3 import Web3
from config.settings import settings, CHAINS
from bot.services.db  import db

logger = logging.getLogger(__name__)

# Minimal ABI — only what we need to monitor
ESCROW_ABI = [
    {"name":"DealFunded",    "type":"event","inputs":[{"name":"id","type":"uint256","indexed":True}]},
    {"name":"DealCompleted", "type":"event","inputs":[{"name":"id","type":"uint256","indexed":True}]},
    {"name":"DealDisputed",  "type":"event","inputs":[{"name":"id","type":"uint256","indexed":True},{"name":"by","type":"address","indexed":False}]},
    {"name":"getStatus",     "type":"function","inputs":[{"name":"dealId","type":"uint256"}],"outputs":[{"name":"","type":"uint8"}],"stateMutability":"view"},
]

STATUS_MAP = {0:"pending_payment",1:"funded",2:"delivered",3:"completed",4:"disputed",5:"refunded",6:"cancelled"}


async def check_deal_on_chain(deal, app=None):
    """Check a single deal's status on-chain and update DB if changed."""
    chain_cfg = CHAINS.get(deal.chain)
    if not chain_cfg or not chain_cfg.get("contract"):
        return

    try:
        w3       = Web3(Web3.HTTPProvider(chain_cfg["rpc"]))
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(chain_cfg["contract"]),
            abi=ESCROW_ABI
        )

        # Get on-chain status
        on_chain_status_int = contract.functions.getStatus(deal.on_chain_id).call()
        on_chain_status     = STATUS_MAP.get(on_chain_status_int, "unknown")

        if on_chain_status != deal.status and on_chain_status != "unknown":
            logger.info(f"Deal #{deal.id}: {deal.status} → {on_chain_status}")
            await db.update_deal_status(deal.id, on_chain_status)

            # Notify parties if app provided
            if app and on_chain_status == "funded":
                await notify_deal_funded(deal, app)
            elif app and on_chain_status == "completed":
                await notify_deal_completed(deal, app)

    except Exception as e:
        logger.debug(f"Monitor error deal #{deal.id}: {e}")


async def notify_deal_funded(deal, app):
    """Notify seller that buyer paid."""
    msg = (
        f"💰 *Deal #{deal.id} Funded!*\n\n"
        f"📦 {deal.description}\n"
        f"🛒 Buyer @{deal.buyer_username} has locked the payment.\n\n"
        f"Deliver the service, then mark as delivered with:\n"
        f"`/delivered {deal.id}`"
    )
    try:
        if deal.seller_tg_id:
            await app.bot.send_message(deal.seller_tg_id, msg, parse_mode="Markdown")
    except Exception:
        pass


async def notify_deal_completed(deal, app):
    """Notify seller that funds were released."""
    msg = (
        f"✅ *Deal #{deal.id} Completed!*\n\n"
        f"💰 {deal.seller_gets} {deal.token} has been released to your wallet."
    )
    try:
        if deal.seller_tg_id:
            await app.bot.send_message(deal.seller_tg_id, msg, parse_mode="Markdown")
    except Exception:
        pass


async def monitor_active_deals(app=None):
    """Check all active deals on-chain."""
    try:
        from sqlalchemy import select
        from bot.services.db import Deal, AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Deal).where(
                    Deal.status.in_(["pending_payment", "funded", "delivered"]),
                    Deal.on_chain_id.isnot(None),
                    Deal.chain.in_(list(CHAINS.keys()))
                ).limit(50)
            )
            deals = result.scalars().all()

        logger.info(f"🔍 Monitoring {len(deals)} active deals on-chain...")
        for deal in deals:
            await check_deal_on_chain(deal, app)
            await asyncio.sleep(0.5)  # avoid rate limiting

    except Exception as e:
        logger.error(f"Monitor error: {e}")
