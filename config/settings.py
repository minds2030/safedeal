"""
config/settings.py — All environment variables & chain config
Copy .env.example to .env and fill in your values
"""

from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    # ── Telegram ───────────────────────────────────────────
    BOT_TOKEN:        str
    MINIAPP_URL:      str   # e.g. https://yourdomain.com/app

    # ── SafeDeal Platform ──────────────────────────────────
    PLATFORM_WALLET_EVM: str   # your ETH/BSC/Polygon wallet
    PLATFORM_WALLET_TON: str   # your TON wallet address
    PLATFORM_FEE_BPS:    int = 200   # 2%

    # ── Database ───────────────────────────────────────────
    DATABASE_URL: str   # postgresql://user:pass@host/db

    # ── EVM RPC endpoints ─────────────────────────────────
    RPC_ETHEREUM:  str = "https://rpc.ankr.com/eth"
    RPC_BSC:       str = "https://bsc-dataseed.binance.org"
    RPC_POLYGON:   str = "https://polygon-rpc.com"
    RPC_BASE:      str = "https://mainnet.base.org"
    RPC_SEPOLIA:   str = "https://rpc.sepolia.org"        # testnet
    RPC_BSC_TEST:  str = "https://data-seed-prebsc-1-s1.binance.org:8545"  # testnet

    # ── Deployed contract addresses ────────────────────────
    CONTRACT_ETHEREUM: str = ""
    CONTRACT_BSC:      str = ""
    CONTRACT_POLYGON:  str = ""
    CONTRACT_BASE:     str = ""
    CONTRACT_SEPOLIA:  str = ""   # testnet
    CONTRACT_BSC_TEST: str = ""   # testnet

    # ── TON ────────────────────────────────────────────────
    TON_ENDPOINT:        str = "https://toncenter.com/api/v2/jsonRPC"
    TON_API_KEY:         str = ""
    TON_CONTRACT_ADDR:   str = ""
    TON_TESTNET_ENDPOINT: str = "https://testnet.toncenter.com/api/v2/jsonRPC"
    TON_TESTNET_CONTRACT: str = ""

    # ── Private key for bot's on-chain actions (auto-release) ─
    BOT_PRIVATE_KEY: str   # EVM private key — keep secret!

    class Config:
        env_file = ".env"


settings = Settings()

# ── Chain metadata (used in UI and deal creation) ─────────
CHAINS: Dict[str, dict] = {
    "ethereum": {
        "name":         "Ethereum",
        "short":        "ETH",
        "icon":         "🔷",
        "rpc":          settings.RPC_ETHEREUM,
        "contract":     settings.CONTRACT_ETHEREUM,
        "chain_id":     1,
        "native":       "ETH",
        "explorer":     "https://etherscan.io",
        "testnet":      False,
        "tokens": {
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        }
    },
    "bsc": {
        "name":         "BNB Chain",
        "short":        "BSC",
        "icon":         "🟡",
        "rpc":          settings.RPC_BSC,
        "contract":     settings.CONTRACT_BSC,
        "chain_id":     56,
        "native":       "BNB",
        "explorer":     "https://bscscan.com",
        "testnet":      False,
        "tokens": {
            "USDT": "0x55d398326f99059fF775485246999027B3197955",
            "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
            "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        }
    },
    "polygon": {
        "name":         "Polygon",
        "short":        "MATIC",
        "icon":         "🟣",
        "rpc":          settings.RPC_POLYGON,
        "contract":     settings.CONTRACT_POLYGON,
        "chain_id":     137,
        "native":       "MATIC",
        "explorer":     "https://polygonscan.com",
        "testnet":      False,
        "tokens": {
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        }
    },
    "base": {
        "name":         "Base",
        "short":        "BASE",
        "icon":         "🔵",
        "rpc":          settings.RPC_BASE,
        "contract":     settings.CONTRACT_BASE,
        "chain_id":     8453,
        "native":       "ETH",
        "explorer":     "https://basescan.org",
        "testnet":      False,
        "tokens": {
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        }
    },
    "ton": {
        "name":         "TON",
        "short":        "TON",
        "icon":         "💎",
        "rpc":          settings.TON_ENDPOINT,
        "contract":     settings.TON_CONTRACT_ADDR,
        "chain_id":     None,   # TON doesn't use EVM chain IDs
        "native":       "TON",
        "explorer":     "https://tonscan.org",
        "testnet":      False,
        "tokens": {
            "USDT": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",  # Jetton master
        }
    },
    # ── Testnets ──────────────────────────────────────────
    "sepolia": {
        "name":     "Sepolia Testnet",
        "short":    "SEP",
        "icon":     "🧪",
        "rpc":      settings.RPC_SEPOLIA,
        "contract": settings.CONTRACT_SEPOLIA,
        "chain_id": 11155111,
        "native":   "ETH",
        "explorer": "https://sepolia.etherscan.io",
        "testnet":  True,
        "tokens":   {}
    },
    "bsc_test": {
        "name":     "BSC Testnet",
        "short":    "TBSC",
        "icon":     "🧪",
        "rpc":      settings.RPC_BSC_TEST,
        "contract": settings.CONTRACT_BSC_TEST,
        "chain_id": 97,
        "native":   "tBNB",
        "explorer": "https://testnet.bscscan.com",
        "testnet":  True,
        "tokens":   {}
    },
    "ton_test": {
        "name":     "TON Testnet",
        "short":    "tTON",
        "icon":     "🧪",
        "rpc":      settings.TON_TESTNET_ENDPOINT,
        "contract": settings.TON_TESTNET_CONTRACT,
        "chain_id": None,
        "native":   "TON",
        "explorer": "https://testnet.tonscan.org",
        "testnet":  True,
        "tokens":   {}
    },
}
