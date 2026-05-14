# 🔐 SafeDeal — Telegram Escrow Bot

Secure escrow for digital service deals on Telegram.
Supports **EVM chains** (ETH/BSC/Polygon/Base) + **TON** natively.

---

## Architecture

```
safedeal/
│
├── contracts/
│   ├── evm/
│   │   └── Escrow.sol          ← One contract, all EVM chains
│   └── ton/
│       └── escrow.fc           ← FunC contract for TON
│
├── bot/
│   ├── handlers/
│   │   ├── start.py            ← /start /help
│   │   ├── deal.py             ← /newdeal /mydeals /deal + callbacks
│   │   ├── wallet.py           ← /wallet /connect
│   │   ├── channel.py          ← /setup /settings + dispute resolution
│   │   └── miniapp.py          ← Mini App web_app_data handler
│   ├── services/
│   │   ├── evm.py              ← Web3 service (all EVM chains)
│   │   ├── ton.py              ← TON service (FunC contract)
│   │   ├── db.py               ← PostgreSQL via SQLAlchemy async
│   │   └── scheduler.py        ← Auto-release background job
│   └── utils/
│       ├── keyboards.py        ← Inline keyboard builders
│       └── formatters.py       ← Deal formatting helpers
│
├── miniapp/                    ← React Mini App (Telegram WebApp)
│   └── src/
│       ├── App.jsx
│       ├── components/
│       └── services/
│           ├── walletConnect.js ← EVM: MetaMask/WalletConnect
│           └── tonConnect.js    ← TON: TON Connect 2.0
│
├── config/
│   └── settings.py             ← All env vars + chain config
│
├── bot.py                      ← Entry point
├── requirements.txt
└── .env.example
```

---

## How It Works

### Deal Flow
```
Seller /newdeal → Bot creates deal in DB
       ↓
Buyer sees payment message with [Fund Deal] button
       ↓
Buyer chooses: 💎 TON Wallet  OR  🦊 MetaMask
       ↓
Mini App opens → user signs transaction with their wallet
       ↓
Funds locked in Smart Contract ✅
       ↓
Seller delivers service
       ↓
Option A: Buyer clicks [Confirm Receipt] → funds released immediately
Option B: Guarantee timer expires → bot auto-releases funds
Option C: Buyer opens dispute → channel admin arbitrates
```

### Fee Structure
```
Buyer pays:  $100
             ├── SafeDeal (2%):      $2  → platform wallet
             ├── Channel owner (1%): $1  → channel wallet
             └── Seller receives:   $97
```

### Networks
| Network  | Type    | Native | Tokens        |
|----------|---------|--------|---------------|
| Ethereum | EVM     | ETH    | USDT, USDC    |
| BSC      | EVM     | BNB    | USDT, BUSD    |
| Polygon  | EVM     | MATIC  | USDT, USDC    |
| Base     | EVM     | ETH    | USDC          |
| TON      | Non-EVM | TON    | USDT (Jetton) |
| Sepolia  | Testnet | ETH    | —             |
| BSC Test | Testnet | tBNB   | —             |
| TON Test | Testnet | TON    | —             |

### EVM vs TON — User's Choice
- User has EVM wallet → pays with MetaMask/WalletConnect on any EVM chain
- User has TON wallet → pays with TON Space (built into Telegram) or TonKeeper
- User has both → they choose per deal — **no restrictions**

---

## Deployment

### 1. Deploy EVM Contract
```bash
cd contracts/evm
npm install
npx hardhat deploy --network bsc
# Repeat for other chains
```

### 2. Compile & Deploy TON Contract
```bash
cd contracts/ton
func -o escrow.fif escrow.fc
fift -s deploy.fif
```

### 3. Setup Bot
```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in .env values
python bot.py
```

### 4. Deploy Mini App
```bash
cd miniapp
npm install && npm run build
# Host on any static server (Vercel, Netlify, etc.)
# Set MINIAPP_URL in .env
```

---

## Channel Owner Setup

1. Add @SafeDealBot to your channel
2. Run `/setup` as admin
3. Run `/settings fee 2` to set your 2% commission
4. Connect your wallet: `/settings wallet evm 0x...`
5. Done! Members can now use `/newdeal`

---

## Revenue Model

- Platform (SafeDeal): **2% fixed** on every deal
- Channel owners: **0-10%** (they set their own rate)
- No subscription fees, no monthly charges
- Pure transaction-based revenue
