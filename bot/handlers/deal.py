"""
bot/handlers/deal.py
Deal handlers — channel cards, deep links, Mini App integration
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config.settings import settings, CHAINS
from bot.services.db      import db
from bot.services.evm     import evm_service
from bot.services.ton     import ton_service
from bot.utils.formatters import format_amount


# ─────────────────────────────────────────────────────────────
# Build the deal card shown in channels
# ─────────────────────────────────────────────────────────────
def build_deal_card(deal, channel=None):
    chain_info = CHAINS.get(deal.chain, {})
    chain_icon = chain_info.get("icon", "🔗")
    chain_name = chain_info.get("name", deal.chain.upper())

    status_line = {
        "pending_payment": "⏳ Awaiting payment from buyer",
        "funded":          "🔒 Funds locked — awaiting delivery",
        "delivered":       "📦 Seller marked as delivered",
        "completed":       "✅ Deal completed successfully",
        "disputed":        "⚠️ Dispute open — under review",
        "refunded":        "↩️ Refunded to buyer",
        "cancelled":       "❌ Deal cancelled",
    }.get(deal.status, "❓")

    channel_fee_line = ""
    if channel and channel.fee_bps > 0:
        channel_fee_line = (
            f"  ├ Channel ({channel.fee_bps/100:.1f}%): "
            f"-{format_amount(deal.channel_fee, deal.token)}\n"
        )

    text = (
        f"🔐 *Escrow Deal #{deal.id}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *{deal.description}*\n\n"
        f"👤 Seller: @{deal.seller_username}\n"
        f"🛒 Buyer: @{deal.buyer_username}\n\n"
        f"💰 *Amount: {format_amount(deal.amount, deal.token)}*\n"
        f"{chain_icon} Network: {chain_name}\n\n"
        f"*Fee breakdown:*\n"
        f"  ├ SafeDeal (2%): -{format_amount(deal.platform_fee, deal.token)}\n"
        f"{channel_fee_line}"
        f"  └ Seller receives: *{format_amount(deal.seller_gets, deal.token)}*\n\n"
        f"⏱ Guarantee: *{deal.guarantee_hours}h* auto-release\n\n"
        f"*Status:* {status_line}"
    )

    deep_link = f"{settings.MINIAPP_URL}?deal_id={deal.id}&action=fund"
    explorer  = chain_info.get("explorer", "https://bscscan.com")
    keyboard  = []

    if deal.status == "pending_payment":
        keyboard.append([InlineKeyboardButton(
            "💳 Fund Deal — Lock Payment",
            web_app=WebAppInfo(url=deep_link)
        )])
        keyboard.append([
            InlineKeyboardButton("📋 Details",  callback_data=f"dealinfo:{deal.id}"),
            InlineKeyboardButton("❌ Cancel",   callback_data=f"cancel:{deal.id}"),
        ])

    elif deal.status in ("funded", "delivered"):
        keyboard.append([
            InlineKeyboardButton(
                "✅ Confirm Receipt",
                web_app=WebAppInfo(url=f"{settings.MINIAPP_URL}?deal_id={deal.id}&action=confirm")
            ),
            InlineKeyboardButton("⚠️ Dispute", callback_data=f"dispute:{deal.id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("📋 Details",  callback_data=f"dealinfo:{deal.id}"),
        ])

    elif deal.status == "disputed":
        keyboard.append([
            InlineKeyboardButton("⚖️ View Dispute", callback_data=f"dealinfo:{deal.id}"),
        ])

    elif deal.status == "completed":
        keyboard.append([
            InlineKeyboardButton("🔍 View on Explorer", url=explorer),
        ])

    return text, InlineKeyboardMarkup(keyboard)


# ─────────────────────────────────────────────────────────────
# /newdeal
# ─────────────────────────────────────────────────────────────
async def new_deal_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # No args → open Mini App
    if not ctx.args:
        kb = [[InlineKeyboardButton(
            "🔐 Open SafeDeal App",
            web_app=WebAppInfo(url=f"{settings.MINIAPP_URL}?action=new_deal")
        )]]
        await update.message.reply_text(
            "👇 Open SafeDeal to create a new escrow deal:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Quick command: /newdeal @buyer amount TOKEN chain hours description
    try:
        buyer_username  = ctx.args[0].lstrip("@")
        amount_str      = ctx.args[1]
        token           = ctx.args[2].upper()
        chain_key       = ctx.args[3].lower()
        hours_str       = ctx.args[4]
        description     = " ".join(ctx.args[5:]) if len(ctx.args) > 5 else "Digital service"
    except IndexError:
        await update.message.reply_text(
            "❌ *Usage:*\n"
            "`/newdeal @buyer amount TOKEN chain hours description`\n\n"
            "*Example:*\n"
            "`/newdeal @john 350 USDT bsc 24h YouTube channel 50K`\n\n"
            "Or just `/newdeal` to open the app 📱",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if chain_key not in CHAINS:
        await update.message.reply_text(
            f"❌ Unknown chain. Available: `{', '.join(CHAINS.keys())}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    amount          = float(amount_str)
    guarantee_hours = int(hours_str.replace("h","").replace("H",""))
    guarantee_secs  = guarantee_hours * 3600

    platform_fee    = amount * (settings.PLATFORM_FEE_BPS / 10000)
    channel         = await db.get_channel(chat.id)
    channel_fee_bps = channel.fee_bps if channel else 0
    channel_fee     = amount * (channel_fee_bps / 10000)
    seller_gets     = amount - platform_fee - channel_fee

    buyer = await db.get_user_by_username(buyer_username)

    deal = await db.create_deal(
        seller_tg_id    = user.id,
        seller_username = user.username or str(user.id),
        buyer_username  = buyer_username,
        buyer_tg_id     = buyer.tg_id if buyer else None,
        chain           = chain_key,
        token           = token,
        amount          = amount,
        seller_gets     = seller_gets,
        platform_fee    = platform_fee,
        channel_fee     = channel_fee,
        guarantee_secs  = guarantee_secs,
        description     = description,
        channel_id      = chat.id,
    )

    text, kb = build_deal_card(deal, channel)
    msg = await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    await db.update_deal_message_id(deal.id, msg.message_id)

    # DM buyer if known
    if buyer:
        try:
            await ctx.bot.send_message(
                chat_id    = buyer.tg_id,
                text       = f"🔔 *New escrow deal from @{user.username}!*\n\n{text}",
                parse_mode = ParseMode.MARKDOWN,
                reply_markup= kb
            )
        except Exception:
            pass

    # Send deep link to seller in DM
    deep_link = f"https://t.me/{ctx.bot.username}?start=deal_{deal.id}"
    try:
        await ctx.bot.send_message(
            chat_id    = user.id,
            text       = (
                f"✅ *Deal #{deal.id} created!*\n\n"
                f"📤 Share this link with the buyer:\n"
                f"`{deep_link}`\n\n"
                f"Or they can tap *Fund Deal* directly from the channel card."
            ),
            parse_mode = ParseMode.MARKDOWN
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Deep link handler — /start deal_123
# ─────────────────────────────────────────────────────────────
async def deep_link_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if not ctx.args:
        return False

    param = ctx.args[0]
    if not param.startswith("deal_"):
        return False

    deal_id = int(param.replace("deal_", ""))
    deal    = await db.get_deal(deal_id)
    if not deal:
        await update.message.reply_text("❌ Deal not found.")
        return True

    channel  = await db.get_channel(deal.channel_id)
    text, kb = build_deal_card(deal, channel)
    await update.message.reply_text(
        f"🔗 *You were invited to an escrow deal:*\n\n{text}",
        parse_mode   = ParseMode.MARKDOWN,
        reply_markup = kb
    )
    return True


# ─────────────────────────────────────────────────────────────
# /deal <id>
# ─────────────────────────────────────────────────────────────
async def deal_info_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /deal <deal_id>")
        return
    deal_id = int(ctx.args[0])
    deal    = await db.get_deal(deal_id)
    if not deal:
        await update.message.reply_text("❌ Deal not found.")
        return
    channel  = await db.get_channel(deal.channel_id)
    text, kb = build_deal_card(deal, channel)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


# ─────────────────────────────────────────────────────────────
# /mydeals
# ─────────────────────────────────────────────────────────────
async def my_deals_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    deals   = await db.get_user_deals(user_id)

    if not deals:
        kb = [[InlineKeyboardButton(
            "➕ Create First Deal",
            web_app=WebAppInfo(url=f"{settings.MINIAPP_URL}?action=new_deal")
        )]]
        await update.message.reply_text("You have no deals yet.", reply_markup=InlineKeyboardMarkup(kb))
        return

    status_emoji = {
        "pending_payment":"⏳","funded":"🔒","delivered":"📦",
        "completed":"✅","disputed":"⚠️","refunded":"↩️","cancelled":"❌"
    }
    text = "📊 *Your Deals*\n\n"
    rows = []
    for d in deals[:8]:
        e     = status_emoji.get(d.status, "❓")
        text += f"{e} *#{d.id}* — {d.description[:28]}\n"
        text += f"   {format_amount(d.amount, d.token)} · {d.chain} · `{d.status}`\n\n"
        rows.append([InlineKeyboardButton(
            f"{e} #{d.id} — {d.description[:22]}",
            callback_data=f"dealinfo:{d.id}"
        )])

    rows.append([InlineKeyboardButton(
        "📱 Open Full App",
        web_app=WebAppInfo(url=settings.MINIAPP_URL)
    )])
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ─────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────
async def deal_info_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    deal_id = int(query.data.split(":")[1])
    deal    = await db.get_deal(deal_id)
    if not deal:
        await query.answer("Deal not found", show_alert=True)
        return
    await query.answer()
    channel  = await db.get_channel(deal.channel_id)
    text, kb = build_deal_card(deal, channel)
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def confirm_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    deal_id = int(query.data.split(":")[1])
    deal    = await db.get_deal(deal_id)
    if not deal or deal.buyer_tg_id != query.from_user.id:
        await query.answer("❌ Not authorized.", show_alert=True)
        return
    if deal.status not in ("funded","delivered"):
        await query.answer("❌ Cannot confirm at this stage.", show_alert=True)
        return
    await query.answer("Processing...")
    try:
        tx   = await (ton_service if deal.chain=="ton" else evm_service).auto_release(deal)
        await db.update_deal_status(deal_id, "completed")
        deal     = await db.get_deal(deal_id)
        channel  = await db.get_channel(deal.channel_id)
        text, kb = build_deal_card(deal, channel)
        await query.edit_message_text(
            text + f"\n\n🔗 Tx: `{tx}`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")


async def dispute_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    deal_id = int(query.data.split(":")[1])
    deal    = await db.get_deal(deal_id)
    if not deal:
        await query.answer("Deal not found.", show_alert=True)
        return
    if query.from_user.id not in (deal.seller_tg_id, deal.buyer_tg_id):
        await query.answer("❌ Not a party to this deal.", show_alert=True)
        return
    await query.answer("Dispute opened.")
    await db.update_deal_status(deal_id, "disputed")
    deal     = await db.get_deal(deal_id)
    channel  = await db.get_channel(deal.channel_id)
    text, kb = build_deal_card(deal, channel)
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

    if channel and channel.admin_tg_id:
        resolve_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Seller Wins",  callback_data=f"resolve:{deal_id}:seller"),
            InlineKeyboardButton("↩️ Refund Buyer", callback_data=f"resolve:{deal_id}:buyer"),
        ],[
            InlineKeyboardButton("⚖️ Split 50/50",   callback_data=f"resolve:{deal_id}:50"),
        ]])
        await ctx.bot.send_message(
            chat_id    = channel.admin_tg_id,
            text       = (
                f"🚨 *Dispute — Deal #{deal_id}*\n\n"
                f"📦 {deal.description}\n"
                f"👤 Seller: @{deal.seller_username}\n"
                f"🛒 Buyer: @{deal.buyer_username}\n"
                f"💰 {format_amount(deal.amount, deal.token)}\n\n"
                f"Your decision:"
            ),
            parse_mode   = ParseMode.MARKDOWN,
            reply_markup = resolve_kb
        )


async def auto_release_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    deal_id = int(query.data.split(":")[1])
    deal    = await db.get_deal(deal_id)
    if not deal:
        await query.answer("Deal not found.", show_alert=True)
        return
    import time
    if deal.guarantee_end and time.time() < deal.guarantee_end:
        remaining = int(deal.guarantee_end - time.time())
        h, m = divmod(remaining//60, 60)
        await query.answer(f"⏱ {h}h {m}m remaining.", show_alert=True)
        return
    await query.answer("Releasing...")
    try:
        tx   = await (ton_service if deal.chain=="ton" else evm_service).auto_release(deal)
        await db.update_deal_status(deal_id, "completed")
        deal     = await db.get_deal(deal_id)
        channel  = await db.get_channel(deal.channel_id)
        text, kb = build_deal_card(deal, channel)
        await query.edit_message_text(
            text + f"\n\n🔗 Tx: `{tx}`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")


# ─────────────────────────────────────────────────────────────
# /delivered <id> — seller marks as delivered
# ─────────────────────────────────────────────────────────────
async def delivered_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /delivered <deal_id>")
        return

    deal_id = int(ctx.args[0])
    deal    = await db.get_deal(deal_id)
    user_id = update.effective_user.id

    if not deal:
        await update.message.reply_text("❌ Deal not found.")
        return
    if deal.seller_tg_id != user_id:
        await update.message.reply_text("❌ Only the seller can mark as delivered.")
        return
    if deal.status != "funded":
        await update.message.reply_text(f"❌ Deal status is `{deal.status}`, not funded.", parse_mode=ParseMode.MARKDOWN)
        return

    await db.update_deal_status(deal_id, "delivered")

    # Notify buyer
    if deal.buyer_tg_id:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirm Receipt",  callback_data=f"confirm:{deal_id}"),
                InlineKeyboardButton("⚠️ Open Dispute",    callback_data=f"dispute:{deal_id}"),
            ]])
            await ctx.bot.send_message(
                chat_id      = deal.buyer_tg_id,
                text         = (
                    f"📦 *Seller marked Deal #{deal_id} as delivered!*\n\n"
                    f"📦 {deal.description}\n\n"
                    f"If you received the service, confirm below.\n"
                    f"If there's a problem, open a dispute.\n\n"
                    f"⏱ Auto-releases in {deal.guarantee_hours}h if no action."
                ),
                parse_mode   = ParseMode.MARKDOWN,
                reply_markup = kb
            )
        except Exception:
            pass

    # Update channel card
    channel  = await db.get_channel(deal.channel_id)
    deal     = await db.get_deal(deal_id)
    text, kb = build_deal_card(deal, channel)

    if deal.channel_id and deal.message_id:
        try:
            await ctx.bot.edit_message_text(
                chat_id      = deal.channel_id,
                message_id   = deal.message_id,
                text         = text,
                parse_mode   = ParseMode.MARKDOWN,
                reply_markup = kb
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ Deal #{deal_id} marked as delivered!\nBuyer has been notified."
    )
