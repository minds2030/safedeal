"""
bot/services/ton.py
TON service — talks to the FunC escrow contract via TonCenter API
Uses pytonlib / tonsdk for message building
"""

import asyncio
import time
from tonsdk.contract.wallet import WalletVersionEnum, Wallets
from tonsdk.utils import to_nano, bytes_to_b64str
from tonsdk.boc import Cell, begin_cell
from pytonlib import TonlibClient
from config.settings import settings, CHAINS

# ── Op codes (must match escrow.fc) ──────────────────────────
OP_CREATE_DEAL      = 0x1
OP_FUND_DEAL        = 0x2
OP_MARK_DELIVERED   = 0x3
OP_CONFIRM_RECEIPT  = 0x4
OP_OPEN_DISPUTE     = 0x5
OP_RESOLVE_DISPUTE  = 0x6
OP_AUTO_RELEASE     = 0x7
OP_CANCEL_DEAL      = 0x8
OP_SET_CHANNEL_FEE  = 0x9

# ── Status codes (must match escrow.fc) ──────────────────────
STATUS = {
    0: "pending_payment",
    1: "funded",
    2: "delivered",
    3: "completed",
    4: "disputed",
    5: "refunded",
    6: "cancelled",
}


class TONService:
    """
    Handles TON-side escrow operations.

    Key difference from EVM:
    - No MetaMask — users use TON Space (built into Telegram) or TonKeeper
    - Messages are cells (BOC format), not calldata hex
    - We build the cell, encode as base64, and the Mini App
      passes it to TON Connect for user signing
    """

    def __init__(self, testnet: bool = False):
        self.testnet  = testnet
        endpoint      = settings.TON_TESTNET_ENDPOINT if testnet else settings.TON_ENDPOINT
        self.endpoint = endpoint
        self.api_key  = settings.TON_API_KEY
        self.contract = (
            settings.TON_TESTNET_CONTRACT if testnet
            else settings.TON_CONTRACT_ADDR
        )

    # ── Build BOC messages (returned to Mini App for TON Connect signing) ──

    def build_create_deal_msg(self, buyer_addr: str, amount_nano: int,
                               guarantee_secs: int, channel_wallet: str,
                               is_jetton: bool, jetton_wallet: str = "") -> str:
        """
        Returns base64 BOC of the create_deal message body.
        Mini App passes this to TON Connect → user signs with TON Space / TonKeeper.
        """
        cell = (
            begin_cell()
            .store_uint(OP_CREATE_DEAL, 32)
            .store_uint(0, 64)                      # query_id
            .store_address(buyer_addr)
            .store_uint(amount_nano, 128)
            .store_uint(guarantee_secs, 32)
            .store_address(channel_wallet)
            .store_uint(1 if is_jetton else 0, 1)
            .store_address(jetton_wallet if is_jetton else "0:" + "0"*64)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_fund_deal_msg(self, deal_id: int) -> str:
        """Buyer funds the deal — attaches TON as value."""
        cell = (
            begin_cell()
            .store_uint(OP_FUND_DEAL, 32)
            .store_uint(0, 64)
            .store_uint(deal_id, 64)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_confirm_msg(self, deal_id: int) -> str:
        """Buyer confirms receipt."""
        cell = (
            begin_cell()
            .store_uint(OP_CONFIRM_RECEIPT, 32)
            .store_uint(0, 64)
            .store_uint(deal_id, 64)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_dispute_msg(self, deal_id: int) -> str:
        """Open dispute."""
        cell = (
            begin_cell()
            .store_uint(OP_OPEN_DISPUTE, 32)
            .store_uint(0, 64)
            .store_uint(deal_id, 64)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_auto_release_msg(self, deal_id: int) -> str:
        """Trigger auto-release (bot sends this after guarantee expires)."""
        cell = (
            begin_cell()
            .store_uint(OP_AUTO_RELEASE, 32)
            .store_uint(0, 64)
            .store_uint(deal_id, 64)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_resolve_msg(self, deal_id: int, seller_pct: int) -> str:
        """Arbitrator resolves dispute."""
        cell = (
            begin_cell()
            .store_uint(OP_RESOLVE_DISPUTE, 32)
            .store_uint(0, 64)
            .store_uint(deal_id, 64)
            .store_uint(seller_pct, 7)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    def build_set_fee_msg(self, fee_bps: int) -> str:
        """Channel owner sets their fee."""
        cell = (
            begin_cell()
            .store_uint(OP_SET_CHANNEL_FEE, 32)
            .store_uint(0, 64)
            .store_uint(fee_bps, 32)
            .end_cell()
        )
        return bytes_to_b64str(cell.to_boc())

    # ── TON Connect payload builder ───────────────────────────

    def ton_connect_payload(self, deal_id: int, op: str,
                             amount_nano: int, **kwargs) -> dict:
        """
        Returns a full TON Connect transaction payload.
        The Mini App passes this directly to the tonconnect-sdk.

        Example usage in Mini App JS:
            const payload = await fetch('/api/ton_payload?deal_id=42&op=fund')
            await tonConnectUI.sendTransaction(payload)
        """
        op_map = {
            "create":  lambda: self.build_create_deal_msg(**kwargs),
            "fund":    lambda: self.build_fund_deal_msg(deal_id),
            "confirm": lambda: self.build_confirm_msg(deal_id),
            "dispute": lambda: self.build_dispute_msg(deal_id),
            "resolve": lambda: self.build_resolve_msg(deal_id, kwargs.get("seller_pct",100)),
        }
        boc = op_map[op]()

        return {
            "validUntil": int(time.time()) + 600,  # 10 min
            "messages": [{
                "address": self.contract,
                "amount":  str(amount_nano),        # nanoTON to attach
                "payload": boc,                     # base64 BOC
            }]
        }

    # ── Read from chain (via TonCenter API) ──────────────────

    async def get_deal_status(self, deal_id: int) -> str:
        """Calls get_deal_status() GET method on the contract."""
        import aiohttp
        params = {
            "address": self.contract,
            "method":  "get_deal_status",
            "stack":   [["num", str(deal_id)]],
        }
        headers = {"X-API-Key": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/runGetMethod",
                json=params, headers=headers
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    result = data["result"]["stack"][0][1]
                    return STATUS.get(int(result, 16), "unknown")
                return "unknown"

    async def get_deal_info(self, deal_id: int) -> dict:
        """Returns (amount, seller_gets, guarantee_end, status)."""
        import aiohttp
        params = {
            "address": self.contract,
            "method":  "get_deal_info",
            "stack":   [["num", str(deal_id)]],
        }
        headers = {"X-API-Key": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/runGetMethod",
                json=params, headers=headers
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    stack = data["result"]["stack"]
                    return {
                        "amount":        int(stack[0][1], 16),
                        "seller_gets":   int(stack[1][1], 16),
                        "guarantee_end": int(stack[2][1], 16),
                        "status":        STATUS.get(int(stack[3][1], 16), "unknown"),
                    }
        return {}

    # ── Bot-sent transactions (auto-release, resolve) ─────────

    async def auto_release(self, deal) -> str:
        """
        Bot wallet sends auto_release message to TON contract.
        Used by the scheduler after guarantee expires.
        """
        from tonsdk.contract.wallet import WalletVersionEnum, Wallets
        from tonsdk.crypto import mnemonic_to_wallet_key

        # Load bot TON wallet from mnemonic
        mnemonic = settings.BOT_TON_MNEMONIC.split()
        pub_key, priv_key = mnemonic_to_wallet_key(mnemonic)
        wallet = Wallets.create(WalletVersionEnum.v4r2, pub_key, priv_key, 0)

        boc_b64 = self.build_auto_release_msg(deal.on_chain_id)
        # Send via TonCenter
        return await self._send_boc(boc_b64, wallet, to_nano(0.05, "ton"))

    async def resolve_dispute(self, deal, seller_pct: int) -> str:
        from tonsdk.crypto import mnemonic_to_wallet_key
        mnemonic = settings.BOT_TON_MNEMONIC.split()
        pub_key, priv_key = mnemonic_to_wallet_key(mnemonic)
        wallet = Wallets.create(WalletVersionEnum.v4r2, pub_key, priv_key, 0)
        boc_b64 = self.build_resolve_msg(deal.on_chain_id, seller_pct)
        return await self._send_boc(boc_b64, wallet, to_nano(0.05, "ton"))

    async def _send_boc(self, boc_b64: str, wallet, amount_nano: int) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/sendBoc",
                json={"boc": boc_b64},
                headers={"X-API-Key": self.api_key}
            ) as r:
                data = await r.json()
                return data.get("result", {}).get("hash", "unknown")


ton_service      = TONService(testnet=False)
ton_service_test = TONService(testnet=True)
