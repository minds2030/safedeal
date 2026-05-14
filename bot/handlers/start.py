"""
bot/handlers/start.py
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config.settings import settings
from bot.services.db import db
from bot.handlers.deal import deep_link_handler


async def start_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username or "")

    if ctx.args:
        handled = await deep_link_handler(update, ctx)
        if handled:
            return

    text = (
        f"👋 Welcome to *SafeDeal*, {user.first_name}!\n\n"
        "🔐 *Secure escrow for digital service deals on Telegram.*\n\n"
        "*How it works:*\n"
        "1️⃣ Seller creates a deal with `/newdeal`\n"
        "2️⃣ Buyer pays — funds lock in smart contract 🔒\n"
        "3️⃣ Seller delivers & runs `/delivered <id>`\n"
        "4️⃣ Buyer confirms ✅ or opens dispute ⚠️\n"
        "5️⃣ No action? Auto-releases after guarantee period ⏱\n\n"
        "*Supported networks:*\n"
        "🔷 ETH  🟡 BSC  🟣 Polygon  🔵 Base  💎 TON\n\n"
        "📢 *Channel owners:* add me & run `/setup` to earn commissions!"
    )

    kb = [
        [InlineKeyboardButton("🔐 Open SafeDeal App", web_app=WebAppInfo(url=settings.MINIAPP_URL))],
        [
            InlineKeyboardButton("➕ New Deal",  callback_data="goto_newdeal"),
            InlineKeyboardButton("📊 My Deals", callback_data="goto_mydeals"),
        ],
        [
            InlineKeyboardButton("👛 Wallet",   callback_data="goto_wallet"),
            InlineKeyboardButton("❓ Help",      callback_data="goto_help"),
        ],
    ]
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def help_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "*SafeDeal — Commands*\n\n"
        "*/newdeal* `@buyer amount TOKEN chain hours desc`\n"
        "  Create a new escrow deal\n\n"
        "*/delivered* `<id>` — Mark service as delivered\n"
        "*/mydeals* — Your active deals\n"
        "*/deal* `<id>` — View deal details\n"
        "*/wallet* — Manage wallets\n"
        "*/connect* `evm|ton <address>` — Link wallet\n\n"
        "*Channel owners:*\n"
        "*/setup* — Activate SafeDeal in your channel\n"
        "*/settings* — Configure fees & guarantee period\n\n"
        "*Example:*\n"
        "`/newdeal @john 350 USDT bsc 24h YouTube 50K channel`\n\n"
        "*Chains:* ethereum, bsc, polygon, base, ton\n"
        "*Testnets:* sepolia, bsc\\_test\n\n"
        "💬 Support: @SafeDealSupport"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
