"""
bot/handlers/wallet.py
Wallet connection — user can connect EVM wallet (MetaMask) AND/OR TON wallet
They're free to choose which one to use per deal
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config.settings import settings
from bot.services.db import db


async def wallet_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db_user = await db.get_or_create_user(user.id, user.username or "")

    evm_wallet = db_user.wallet_evm or "Not connected"
    ton_wallet = db_user.wallet_ton or "Not connected"
    preferred  = db_user.preferred_chain or "bsc"

    evm_short = f"`{db_user.wallet_evm[:6]}...{db_user.wallet_evm[-4:]}`" if db_user.wallet_evm else "❌ Not connected"
    ton_short = f"`{db_user.wallet_ton[:8]}...`"                          if db_user.wallet_ton else "❌ Not connected"

    text = (
        "👛 *Your Wallets*\n\n"
        f"🔷 *EVM Wallet* (ETH/BSC/Polygon/Base)\n"
        f"   {evm_short}\n\n"
        f"💎 *TON Wallet*\n"
        f"   {ton_short}\n\n"
        f"⭐ *Preferred chain:* {preferred}\n\n"
        "You can connect both — SafeDeal will use the right one per deal, "
        "or you can always choose manually when creating a deal."
    )

    kb = [
        [InlineKeyboardButton(
            "🦊 Connect EVM Wallet (MetaMask/WalletConnect)",
            web_app=WebAppInfo(url=f"{settings.MINIAPP_URL}?action=connect_evm&tg_id={user.id}")
        )],
        [InlineKeyboardButton(
            "💎 Connect TON Wallet (TON Space / TonKeeper)",
            web_app=WebAppInfo(url=f"{settings.MINIAPP_URL}?action=connect_ton&tg_id={user.id}")
        )],
        [InlineKeyboardButton(
            f"⭐ Preferred: {preferred}  (tap to change)",
            callback_data="change_preferred"
        )],
    ]

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def connect_wallet_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /connect <chain> <address>
    e.g. /connect evm 0x742d35Cc...
         /connect ton UQAbc...
    """
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "`/connect evm 0xYourEVMAddress`\n"
            "`/connect ton YourTONAddress`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    chain   = ctx.args[0].lower()
    address = ctx.args[1]
    user    = update.effective_user

    if chain == "evm":
        if not address.startswith("0x") or len(address) != 42:
            await update.message.reply_text("❌ Invalid EVM address. Should be 0x... (42 chars)")
            return
        await db.update_user_wallet(user.id, "evm", address)
        await update.message.reply_text(
            f"✅ EVM wallet connected!\n`{address}`\n\n"
            "Now you can fund deals using MetaMask, WalletConnect, or any EVM wallet.",
            parse_mode=ParseMode.MARKDOWN
        )

    elif chain == "ton":
        if len(address) < 48:
            await update.message.reply_text("❌ Invalid TON address.")
            return
        await db.update_user_wallet(user.id, "ton", address)
        await update.message.reply_text(
            f"✅ TON wallet connected!\n`{address}`\n\n"
            "Now you can fund deals using TON Space (built into Telegram) or TonKeeper.",
            parse_mode=ParseMode.MARKDOWN
        )

    else:
        await update.message.reply_text("❌ Chain must be `evm` or `ton`", parse_mode=ParseMode.MARKDOWN)
