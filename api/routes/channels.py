"""
api/routes/channels.py
Channel endpoints — settings, fees, dispute management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from bot.services.db import db

router = APIRouter()


class ChannelResponse(BaseModel):
    tg_id:          int
    title:          str
    fee_bps:        int
    fee_pct:        float
    guarantee_hours: int
    can_arbitrate:  bool
    wallet_evm:     Optional[str]
    wallet_ton:     Optional[str]
    testnet_mode:   bool
    support_link:   Optional[str] = None


class UpdateChannelRequest(BaseModel):
    tg_id:          int
    admin_tg_id:    int
    fee_bps:        Optional[int]      = None
    guarantee_secs: Optional[int]      = None
    wallet_evm:     Optional[str]      = None
    wallet_ton:     Optional[str]      = None
    can_arbitrate:  Optional[bool]     = None
    testnet_mode:   Optional[bool]     = None


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int):
    ch = await db.get_channel(channel_id)
    if not ch:
        raise HTTPException(404, "Channel not found — run /setup first")
    return ChannelResponse(
        tg_id           = ch.tg_id,
        title           = ch.title,
        fee_bps         = ch.fee_bps,
        fee_pct         = ch.fee_bps / 100,
        guarantee_hours = ch.guarantee_secs // 3600,
        can_arbitrate   = ch.can_arbitrate,
        wallet_evm      = ch.wallet_evm,
        wallet_ton      = ch.wallet_ton,
        testnet_mode    = ch.testnet_mode,
    )


@router.post("/update")
async def update_channel(req: UpdateChannelRequest):
    ch = await db.get_channel(req.tg_id)
    if not ch:
        raise HTTPException(404, "Channel not found")
    if ch.admin_tg_id != req.admin_tg_id:
        raise HTTPException(403, "Not channel admin")

    updates = {}
    if req.fee_bps is not None:
        if req.fee_bps > 1000:
            raise HTTPException(400, "Max fee is 10%")
        updates["fee_bps"] = req.fee_bps
    if req.guarantee_secs is not None:
        updates["guarantee_secs"] = req.guarantee_secs
    if req.wallet_evm is not None:
        updates["wallet_evm"] = req.wallet_evm
    if req.wallet_ton is not None:
        updates["wallet_ton"] = req.wallet_ton
    if req.can_arbitrate is not None:
        updates["can_arbitrate"] = req.can_arbitrate
    if req.testnet_mode is not None:
        updates["testnet_mode"] = req.testnet_mode

    if updates:
        await db.upsert_channel(tg_id=req.tg_id, **updates)

    return {"ok": True, "updated": list(updates.keys())}


@router.get("/{channel_id}/stats")
async def channel_stats(channel_id: int):
    """Stats for channel dashboard."""
    from sqlalchemy import select, func
    from bot.services.db import Deal

    async with db.AsyncSessionLocal() as s:
        total_q = await s.execute(
            select(func.count(Deal.id)).where(Deal.channel_id == channel_id)
        )
        active_q = await s.execute(
            select(func.count(Deal.id)).where(
                Deal.channel_id == channel_id,
                Deal.status.in_(["funded", "delivered"])
            )
        )
        completed_q = await s.execute(
            select(func.count(Deal.id), func.sum(Deal.channel_fee)).where(
                Deal.channel_id == channel_id,
                Deal.status == "completed"
            )
        )
        disputed_q = await s.execute(
            select(func.count(Deal.id)).where(
                Deal.channel_id == channel_id,
                Deal.status == "disputed"
            )
        )

        total      = total_q.scalar() or 0
        active     = active_q.scalar() or 0
        comp_row   = completed_q.first()
        completed  = comp_row[0] or 0
        earned     = float(comp_row[1] or 0)
        disputed   = disputed_q.scalar() or 0

    return {
        "total_deals":   total,
        "active_deals":  active,
        "completed":     completed,
        "disputed":      disputed,
        "total_earned":  round(earned, 4),
    }
