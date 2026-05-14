def format_amount(amount, token):
    return f"{amount:.4f} {token}".rstrip('0').rstrip('.')

def format_deal(deal):
    status_emoji = {
        "pending_payment": "⏳",
        "funded": "🔒",
        "delivered": "📦",
        "completed": "✅",
        "disputed": "⚠️",
        "refunded": "↩️",
        "cancelled": "❌"
    }.get(deal.status, "❓")

    return (
        f"{status_emoji} *Deal #{deal.id}*\n\n"
        f"📦 {deal.description}\n"
        f"💰 {format_amount(deal.amount, deal.token)} on {deal.chain}\n"
        f"👤 Seller: @{deal.seller_username}\n"
        f"🛒 Buyer: @{deal.buyer_username}\n"
        f"📊 Status: `{deal.status}`"
    ) 
