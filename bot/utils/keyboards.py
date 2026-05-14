from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def chain_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟡 BSC", callback_data="chain:bsc"),
        InlineKeyboardButton("🔷 ETH", callback_data="chain:ethereum"),
    ],[
        InlineKeyboardButton("🟣 Polygon", callback_data="chain:polygon"),
        InlineKeyboardButton("🔵 Base", callback_data="chain:base"),
    ],[
        InlineKeyboardButton("💎 TON", callback_data="chain:ton"),
        InlineKeyboardButton("🧪 Testnet", callback_data="chain:sepolia"),
    ]])

def deal_keyboard(deal, is_seller, is_buyer):
    rows = []
    if is_buyer and deal.status in ("funded", "delivered"):
        rows.append([
            InlineKeyboardButton("✅ Confirm Receipt", callback_data=f"confirm:{deal.id}"),
            InlineKeyboardButton("⚠️ Dispute", callback_data=f"dispute:{deal.id}"),
        ])
    if deal.status in ("funded", "delivered"):
        rows.append([InlineKeyboardButton("⏱ Auto Release", callback_data=f"autorelease:{deal.id}")])
    return InlineKeyboardMarkup(rows) if rows else None

def wallet_choice_keyboard(deal_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🦊 MetaMask / WalletConnect", callback_data=f"fund_evm:{deal_id}"),
        InlineKeyboardButton("💎 TON Wallet", callback_data=f"fund_ton:{deal_id}"),
    ]]) 
