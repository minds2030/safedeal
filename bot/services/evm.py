"""
bot/services/evm.py
Web3 service for all EVM chains (ETH, BSC, Polygon, Base, testnets)
One service, all chains — that's the power of EVM compatibility
"""

import json
import os
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from config.settings import settings, CHAINS

# ── Load ABI ──────────────────────────────────────────────────
ABI_PATH = os.path.join(os.path.dirname(__file__), "../../contracts/evm/abi.json")
with open(ABI_PATH) as f:
    ESCROW_ABI = json.load(f)

# ERC-20 minimal ABI (approve + transfer)
ERC20_ABI = [
    {"name":"approve","type":"function","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable"},
    {"name":"decimals","type":"function","inputs":[],"outputs":[{"name":"","type":"uint8"}],"stateMutability":"view"},
    {"name":"balanceOf","type":"function","inputs":[{"name":"account","type":"address"}],"outputs":[{"name":"","type":"uint256"}],"stateMutability":"view"},
]


class EVMService:
    """
    Handles all interactions with the SafeDeal Escrow contract on EVM chains.
    The bot wallet is used only for auto-release (a permissionless public function).
    All user-facing transactions (fund, confirm, dispute) are signed client-side.
    """

    def __init__(self):
        self._w3_cache: dict[str, Web3] = {}
        self.bot_account = Account.from_key(settings.BOT_PRIVATE_KEY)

    def get_w3(self, chain: str) -> Web3:
        """Get (or cache) a Web3 instance for a given chain."""
        if chain not in self._w3_cache:
            cfg = CHAINS[chain]
            w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
            # BSC and Polygon need PoA middleware
            if chain in ("bsc", "polygon", "bsc_test"):
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            self._w3_cache[chain] = w3
        return self._w3_cache[chain]

    def get_contract(self, chain: str):
        w3  = self.get_w3(chain)
        cfg = CHAINS[chain]
        return w3.eth.contract(
            address=Web3.to_checksum_address(cfg["contract"]),
            abi=ESCROW_ABI
        )

    # ── Read functions ────────────────────────────────────────

    def get_deal(self, chain: str, deal_id: int) -> dict:
        contract = self.get_contract(chain)
        d = contract.functions.getDeal(deal_id).call()
        return {
            "id":            d[0],
            "seller":        d[1],
            "buyer":         d[2],
            "token":         d[3],
            "amount":        d[4],
            "seller_gets":   d[5],
            "platform_fee":  d[6],
            "channel_fee":   d[7],
            "channel_wallet":d[8],
            "guarantee_end": d[9],
            "status":        d[10],
            "description":   d[11],
            "created_at":    d[12],
        }

    def is_expired(self, chain: str, deal_id: int) -> bool:
        contract = self.get_contract(chain)
        return contract.functions.isExpired(deal_id).call()

    # ── Build unsigned transactions (returned to frontend for user signing) ──

    def build_create_deal_tx(self, chain: str, seller: str, buyer: str,
                              token_symbol: str, amount_human: float,
                              guarantee_secs: int, channel_wallet: str,
                              description: str) -> dict:
        """
        Builds the createDeal() transaction — signed by the SELLER via MetaMask.
        Returns a tx dict that the Mini App sends to MetaMask/WalletConnect.
        """
        w3       = self.get_w3(chain)
        contract = self.get_contract(chain)
        cfg      = CHAINS[chain]

        token_addr = cfg["tokens"].get(token_symbol)
        is_native  = token_addr is None

        if is_native:
            token_addr_cs = "0x0000000000000000000000000000000000000000"
            decimals      = 18
        else:
            token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)
            decimals       = token_contract.functions.decimals().call()
            token_addr_cs  = Web3.to_checksum_address(token_addr)

        amount_wei = int(amount_human * (10 ** decimals))

        tx = contract.functions.createDeal(
            Web3.to_checksum_address(buyer),
            token_addr_cs,
            amount_wei,
            guarantee_secs,
            Web3.to_checksum_address(channel_wallet),
            description
        ).build_transaction({
            "from":     Web3.to_checksum_address(seller),
            "chainId":  cfg["chain_id"],
            "gas":      300000,
            "gasPrice": w3.eth.gas_price,
            "nonce":    w3.eth.get_transaction_count(Web3.to_checksum_address(seller)),
        })
        return tx

    def build_fund_deal_tx(self, chain: str, buyer: str,
                            deal_id: int, token_symbol: str,
                            amount_human: float) -> dict:
        """
        Builds the fundDeal() transaction — signed by the BUYER.
        If ERC-20: also returns an approve() tx to send first.
        """
        w3       = self.get_w3(chain)
        contract = self.get_contract(chain)
        cfg      = CHAINS[chain]

        token_addr = cfg["tokens"].get(token_symbol)
        is_native  = token_addr is None

        if is_native:
            decimals  = 18
            amount_wei = int(amount_human * (10 ** decimals))
            fund_tx = contract.functions.fundDeal(deal_id).build_transaction({
                "from":     Web3.to_checksum_address(buyer),
                "chainId":  cfg["chain_id"],
                "value":    amount_wei,
                "gas":      200000,
                "gasPrice": w3.eth.gas_price,
                "nonce":    w3.eth.get_transaction_count(Web3.to_checksum_address(buyer)),
            })
            return {"approve_tx": None, "fund_tx": fund_tx}
        else:
            token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)
            decimals       = token_contract.functions.decimals().call()
            amount_wei     = int(amount_human * (10 ** decimals))
            nonce          = w3.eth.get_transaction_count(Web3.to_checksum_address(buyer))

            approve_tx = token_contract.functions.approve(
                cfg["contract"], amount_wei
            ).build_transaction({
                "from": Web3.to_checksum_address(buyer),
                "chainId": cfg["chain_id"],
                "gas": 100000,
                "gasPrice": w3.eth.gas_price,
                "nonce": nonce,
            })
            fund_tx = contract.functions.fundDeal(deal_id).build_transaction({
                "from":     Web3.to_checksum_address(buyer),
                "chainId":  cfg["chain_id"],
                "value":    0,
                "gas":      200000,
                "gasPrice": w3.eth.gas_price,
                "nonce":    nonce + 1,
            })
            return {"approve_tx": approve_tx, "fund_tx": fund_tx}

    def build_confirm_tx(self, chain: str, buyer: str, deal_id: int) -> dict:
        w3       = self.get_w3(chain)
        contract = self.get_contract(chain)
        cfg      = CHAINS[chain]
        return contract.functions.confirmReceipt(deal_id).build_transaction({
            "from":     Web3.to_checksum_address(buyer),
            "chainId":  cfg["chain_id"],
            "gas":      200000,
            "gasPrice": w3.eth.gas_price,
            "nonce":    w3.eth.get_transaction_count(Web3.to_checksum_address(buyer)),
        })

    def build_dispute_tx(self, chain: str, sender: str, deal_id: int) -> dict:
        w3       = self.get_w3(chain)
        contract = self.get_contract(chain)
        cfg      = CHAINS[chain]
        return contract.functions.openDispute(deal_id).build_transaction({
            "from":     Web3.to_checksum_address(sender),
            "chainId":  cfg["chain_id"],
            "gas":      150000,
            "gasPrice": w3.eth.gas_price,
            "nonce":    w3.eth.get_transaction_count(Web3.to_checksum_address(sender)),
        })

    # ── Bot-signed transactions (auto-release — permissionless) ──

    async def auto_release(self, deal) -> str:
        """Bot calls autoRelease() after guarantee period — no user needed."""
        w3       = self.get_w3(deal.chain)
        contract = self.get_contract(deal.chain)
        cfg      = CHAINS[deal.chain]

        tx = contract.functions.autoRelease(deal.on_chain_id).build_transaction({
            "from":     self.bot_account.address,
            "chainId":  cfg["chain_id"],
            "gas":      250000,
            "gasPrice": w3.eth.gas_price,
            "nonce":    w3.eth.get_transaction_count(self.bot_account.address),
        })
        signed = self.bot_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return receipt.transactionHash.hex()

    async def resolve_dispute(self, deal, seller_pct: int) -> str:
        """Bot (acting as arbitrator) calls resolveDispute()."""
        w3       = self.get_w3(deal.chain)
        contract = self.get_contract(deal.chain)
        cfg      = CHAINS[deal.chain]

        tx = contract.functions.resolveDispute(deal.on_chain_id, seller_pct).build_transaction({
            "from":     self.bot_account.address,
            "chainId":  cfg["chain_id"],
            "gas":      300000,
            "gasPrice": w3.eth.gas_price,
            "nonce":    w3.eth.get_transaction_count(self.bot_account.address),
        })
        signed = self.bot_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return receipt.transactionHash.hex()


evm_service = EVMService()
