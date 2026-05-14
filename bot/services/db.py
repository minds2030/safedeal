"""
bot/services/db.py
Database service — PostgreSQL via SQLAlchemy async
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, BigInteger, Integer, String, Float,
    DateTime, Boolean, Text, select, update
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

Base = declarative_base()
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Models ────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    tg_id          = Column(BigInteger, primary_key=True)
    username       = Column(String(64), index=True)
    wallet_evm     = Column(String(42))   # MetaMask/WalletConnect address
    wallet_ton     = Column(String(68))   # TON wallet address
    preferred_chain = Column(String(20), default="bsc")
    created_at     = Column(DateTime, default=datetime.utcnow)


class Deal(Base):
    __tablename__ = "deals"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    on_chain_id     = Column(Integer)          # contract's deal ID
    seller_tg_id    = Column(BigInteger, index=True)
    seller_username = Column(String(64))
    buyer_tg_id     = Column(BigInteger, index=True, nullable=True)
    buyer_username  = Column(String(64))
    chain           = Column(String(20))       # "bsc", "ton", "polygon", etc.
    token           = Column(String(10))       # "USDT", "TON", "ETH"
    amount          = Column(Float)
    seller_gets     = Column(Float)
    platform_fee    = Column(Float)
    channel_fee     = Column(Float)
    guarantee_secs  = Column(Integer)
    guarantee_end   = Column(Integer)          # unix timestamp
    guarantee_hours = Column(Integer)
    description     = Column(Text)
    status          = Column(String(20), default="pending_payment", index=True)
    channel_id      = Column(BigInteger)       # Telegram group/channel ID
    message_id      = Column(BigInteger)       # Bot's message in the group
    created_at      = Column(DateTime, default=datetime.utcnow)
    completed_at    = Column(DateTime, nullable=True)


class Channel(Base):
    __tablename__ = "channels"
    tg_id          = Column(BigInteger, primary_key=True)
    title          = Column(String(128))
    admin_tg_id    = Column(BigInteger)
    admin_username = Column(String(64))
    wallet_evm     = Column(String(42))
    wallet_ton     = Column(String(68))
    fee_bps        = Column(Integer, default=100)   # 1% default
    guarantee_secs = Column(Integer, default=86400) # 24h default
    can_arbitrate  = Column(Boolean, default=True)
    testnet_mode   = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)


# ── DB Service ────────────────────────────────────────────────

class DBService:
    async def init(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ── User ──────────────────────────────────────────────────

    async def get_or_create_user(self, tg_id: int, username: str) -> User:
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(User).where(User.tg_id == tg_id))
            user = result.scalar_one_or_none()
            if not user:
                user = User(tg_id=tg_id, username=username)
                s.add(user)
                await s.commit()
                await s.refresh(user)
            return user

    async def get_user_by_username(self, username: str) -> Optional[User]:
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()

    async def update_user_wallet(self, tg_id: int, chain: str, address: str):
        """Store wallet address — evm or ton."""
        async with AsyncSessionLocal() as s:
            field = User.wallet_evm if chain != "ton" else User.wallet_ton
            await s.execute(update(User).where(User.tg_id == tg_id).values({field: address}))
            await s.commit()

    # ── Deal ──────────────────────────────────────────────────

    async def create_deal(self, **kwargs) -> Deal:
        import math
        secs = kwargs.get("guarantee_secs", 86400)
        kwargs["guarantee_hours"] = secs // 3600
        async with AsyncSessionLocal() as s:
            deal = Deal(**kwargs)
            s.add(deal)
            await s.commit()
            await s.refresh(deal)
            return deal

    async def get_deal(self, deal_id: int) -> Optional[Deal]:
        async with AsyncSessionLocal() as s:
            return await s.get(Deal, deal_id)

    async def get_user_deals(self, tg_id: int) -> List[Deal]:
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Deal).where(
                    (Deal.seller_tg_id == tg_id) | (Deal.buyer_tg_id == tg_id)
                ).order_by(Deal.created_at.desc()).limit(20)
            )
            return result.scalars().all()

    async def update_deal_status(self, deal_id: int, status: str):
        async with AsyncSessionLocal() as s:
            values = {"status": status}
            if status == "completed":
                values["completed_at"] = datetime.utcnow()
            await s.execute(update(Deal).where(Deal.id == deal_id).values(values))
            await s.commit()

    async def update_deal_message_id(self, deal_id: int, message_id: int):
        async with AsyncSessionLocal() as s:
            await s.execute(update(Deal).where(Deal.id == deal_id).values(message_id=message_id))
            await s.commit()

    async def update_deal_on_chain_id(self, deal_id: int, on_chain_id: int, guarantee_end: int):
        async with AsyncSessionLocal() as s:
            await s.execute(
                update(Deal).where(Deal.id == deal_id)
                .values(on_chain_id=on_chain_id, guarantee_end=guarantee_end)
            )
            await s.commit()

    async def get_expired_deals(self, now: int) -> List[Deal]:
        """Deals that are funded/delivered and whose guarantee has expired."""
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Deal).where(
                    Deal.status.in_(["funded", "delivered"]),
                    Deal.guarantee_end <= now,
                    Deal.guarantee_end > 0,
                )
            )
            return result.scalars().all()

    async def get_stale_disputes(self, hours: int = 24) -> List[Deal]:
        from sqlalchemy import func
        cutoff = datetime.utcnow().timestamp() - (hours * 3600)
        async with AsyncSessionLocal() as s:
            result = await s.execute(
                select(Deal).where(
                    Deal.status == "disputed",
                    Deal.guarantee_end < cutoff,
                )
            )
            return result.scalars().all()

    # ── Channel ───────────────────────────────────────────────

    async def get_channel(self, tg_id: int) -> Optional[Channel]:
        async with AsyncSessionLocal() as s:
            return await s.get(Channel, tg_id)

    async def upsert_channel(self, **kwargs) -> Channel:
        async with AsyncSessionLocal() as s:
            ch = await s.get(Channel, kwargs["tg_id"])
            if not ch:
                ch = Channel(**kwargs)
                s.add(ch)
            else:
                for k, v in kwargs.items():
                    setattr(ch, k, v)
            await s.commit()
            await s.refresh(ch)
            return ch

    async def update_channel_fee(self, tg_id: int, fee_bps: int):
        async with AsyncSessionLocal() as s:
            await s.execute(update(Channel).where(Channel.tg_id == tg_id).values(fee_bps=fee_bps))
            await s.commit()


db = DBService()
