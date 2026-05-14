"""
bot/handlers/channel.py — Channel owner setup & settings
bot/handlers/admin.py   — Dispute resolution by arbitrator
bot/handlers/miniapp.py — Mini App web_app_data handler
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from bot.services.db  import db
from bot.services.evm import evm_service
from bot.services.ton import ton_service
from bot.utils.formatters import format_amount


# ══════════════════════════════════════════════════════════════
# channel.py
# ══════════════════════════════════════════════════════════════

async def channel_setup_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /setup — Channel owner registers their channel with SafeDeal.
    Must be run inside the channel/group by an admin.
    """
    chat = update.effective_chat
    user = update.effective_user

    # Verify admin
    member = await ctx.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ Only channel admins can run /setup")
        return

    await db.upsert_channel(
        tg_id          = chat.id,
        title          = chat.title or "Unknown",
        admin_tg_id    = user.id,
        admin_username = user.username or "",
        fee_bps        = 100,   # default 1%
        guarantee_secs = 86400, # default 24h
    )

    text = (
        f"✅ *SafeDeal activated for {chat.title}!*\n\n"
        "Default settings:\n"
        "  💰 Your commission: *1%* per deal\n"
        "  ⏱ Guarantee period: *24 hours*\n"
        "  ⚖️ You can arbitrate disputes: *Yes*\n\n"
        "Next steps:\n"
        "1️⃣ Connect your wallet — /settings\n"
        "2️⃣ Set your commission — /settings\n"
        "3️⃣ Announce to your community!\n\n"
        "Members can now create deals with /newdeal"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def channel_settings_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /settings — Show and update channel settings.
    Usage: /settings fee 2          → set commission to 2%
           /settings guarantee 48   → set guarantee to 48h
           /settings wallet evm 0x... → set payout wallet
    """
    chat = update.effective_chat
    user = update.effective_user

    member = await ctx.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("❌ Admin only.")
        return

    channel = await db.get_channel(chat.id)
    if not channel:
        await update.message.reply_text("❌ Run /setup first to activate SafeDeal.")
        return

    # If args provided, update a setting
    if ctx.args:
        setting = ctx.args[0].lower()
        if setting == "fee" and len(ctx.args) > 1:
            bps = int(float(ctx.args[1]) * 100)  # e.g. 2 → 200 bps
            if bps > 1000:
                await update.message.reply_text("❌ Max commission is 10%")
                return
            await db.update_channel_fee(chat.id, bps)
            await update.message.reply_text(f"✅ Commission set to {bps/100}%")
            return

        if setting == "guarantee" and len(ctx.args) > 1:
            hours = int(ctx.args[1])
            await db.upsert_channel(tg_id=chat.id, guarantee_secs=hours*3600)
            await update.message.reply_text(f"✅ Guarantee period set to {hours} hours")
            return

        if setting == "wallet" and len(ctx.args) > 2:
            chain, addr = ctx.args[1].lower(), ctx.args[2]
            field = "wallet_evm" if chain == "evm" else "wallet_ton"
            await db.upsert_channel(tg_id=chat.id, **{field: addr})
            await update.message.reply_text(f"✅ {chain.upper()} wallet updated: `{addr}`", parse_mode=ParseMode.MARKDOWN)
            return

    # Show current settings
    evm_w = f"`{channel.wallet_evm[:6]}...{channel.wallet_evm[-4:]}`" if channel.wallet_evm else "❌ Not set"
    ton_w = f"`{channel.wallet_ton[:8]}...`"                          if channel.wallet_ton else "❌ Not set"

    text = (
        f"⚙️ *SafeDeal Settings — {chat.title}*\n\n"
        f"💰 Commission: *{channel.fee_bps/100}%* per deal\n"
        f"⏱ Default guarantee: *{channel.guarantee_secs//3600}h*\n"
        f"⚖️ Can arbitrate: *{'Yes' if channel.can_arbitrate else 'No'}*\n"
        f"🧪 Testnet mode: *{'ON' if channel.testnet_mode else 'OFF'}*\n\n"
        f"🔷 EVM wallet: {evm_w}\n"
        f"💎 TON wallet: {ton_w}\n\n"
        "*Commands to update:*\n"
        "`/settings fee 2` → set 2% commission\n"
        "`/settings guarantee 48` → 48h guarantee\n"
        "`/settings wallet evm 0x...` → EVM payout wallet\n"
        "`/settings wallet ton UQ...` → TON payout wallet"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ══════════════════════════════════════════════════════════════
# admin.py — Dispute resolution
# ══════════════════════════════════════════════════════════════

async def resolve_dispute_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Callback: resolve:<deal_id>:seller | buyer | 50
    Only channel admin or SafeDeal can call this.
    """
    query = update.callback_query
    await query.answer()

    parts   = query.data.split(":")
    deal_id = int(parts[1])
    verdict = parts[2]   # "seller", "buyer", or a number like "50"

    deal = await db.get_deal(deal_id)
    if not deal:
        await query.edit_message_text("❌ Deal not found.")
        return

    if deal.status != "disputed":
        await query.edit_message_text("❌ Deal is not in dispute.")
        return

    # Map verdict to seller_pct
    if verdict == "seller":
        seller_pct = 100
    elif verdict == "buyer":
        seller_pct = 0
    else:
        seller_pct = int(verdict)

    try:
        if deal.chain == "ton":
            tx = await ton_service.resolve_dispute(deal, seller_pct)
        else:
            tx = await evm_service.resolve_dispute(deal, seller_pct)

        new_status = "completed" if seller_pct > 0 else "refunded"
        await db.update_deal_status(deal_id, new_status)

        result_text = (
            f"⚖️ *Dispute Resolved — Deal #{deal_id}*\n\n"
            f"📦 {deal.description}\n\n"
        )
        if seller_pct == 100:
            result_text += f"✅ Full amount released to seller @{deal.seller_username}"
        elif seller_pct == 0:
            result_text += f"↩️ Full refund sent to buyer @{deal.buyer_username}"
        else:
            result_text += (
                f"⚖️ Split {seller_pct}/{100-seller_pct}:\n"
                f"  Seller @{deal.seller_username}: {format_amount(deal.seller_gets * seller_pct/100, deal.token)}\n"
                f"  Buyer @{deal.buyer_username}: {format_amount(deal.amount * (100-seller_pct)/100, deal.token)}"
            )
        result_text += f"\n\n🔗 Tx: `{tx}`"

        await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)

        # Notify both parties
        for tg_id, name in [(deal.seller_tg_id, deal.seller_username), (deal.buyer_tg_id, deal.buyer_username)]:
            if tg_id:
                try:
                    await ctx.bot.send_message(chat_id=tg_id, text=result_text, parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    pass

    except Exception as e:
        await query.edit_message_text(f"❌ On-chain error: {e}")


# ══════════════════════════════════════════════════════════════
# miniapp.py — Mini App handlers
# ══════════════════════════════════════════════════════════════

import json

async def miniapp_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Open the Mini App."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    kb = [[InlineKeyboardButton("🔐 SafeDeal App", web_app=WebAppInfo(url=settings.MINIAPP_URL))]]
    from config.settings import settings
    await update.message.reply_text("Open SafeDeal:", reply_markup=InlineKeyboardMarkup(kb))


async def webapp_data_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Handles data sent FROM the Mini App to the bot via sendData().
    The Mini App sends JSON with action + payload.
    """
    raw  = update.message.web_app_data.data
    data = json.loads(raw)
    action = data.get("action")

    if action == "wallet_connected":
        chain   = data["chain"]   # "evm" or "ton"
        address = data["address"]
        await db.update_user_wallet(update.effective_user.id, chain, address)
        await update.message.reply_text(
            f"✅ {chain.upper()} wallet saved: `{address[:10]}...`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "deal_created":
        # Mini App confirmed deal was created on-chain
        deal_id      = data["deal_id"]
        on_chain_id  = data["on_chain_id"]
        guarantee_end = data["guarantee_end"]
        await db.update_deal_on_chain_id(deal_id, on_chain_id, guarantee_end)
        await update.message.reply_text(f"✅ Deal #{deal_id} confirmed on-chain!")

    elif action == "deal_funded":
        deal_id = data["deal_id"]
        tx_hash = data["tx_hash"]
        await db.update_deal_status(deal_id, "funded")
        await update.message.reply_text(
            f"✅ Deal #{deal_id} funded!\nTx: `{tx_hash}`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "channel_fee_set":
        fee_bps = data["fee_bps"]
        await db.update_channel_fee(update.effective_chat.id, fee_bps)
        await update.message.reply_text(f"✅ Channel fee set to {fee_bps/100}%")
