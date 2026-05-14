"""
bot/services/ton.py
TON service — placeholder
"""

class TONService:
    async def auto_release(self, deal) -> str:
        return "ton_not_configured"
    async def resolve_dispute(self, deal, seller_pct: int) -> str:
        return "ton_not_configured"
    async def open_dispute(self, deal) -> str:
        return "ton_not_configured"
    async def confirm_receipt(self, deal) -> str:
        return "ton_not_configured"
    def ton_connect_payload(self, *args, **kwargs) -> dict:
        return {}
    def build_fund_deal_msg(self, deal_id: int) -> str:
        return ""
    def build_confirm_msg(self, deal_id: int) -> str:
        return ""
    def build_dispute_msg(self, deal_id: int) -> str:
        return ""

ton_service      = TONService()
ton_service_test = TONService()
