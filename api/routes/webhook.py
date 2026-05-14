"""
api/routes/webhook.py
Webhook endpoints — Mini App sends events here after on-chain actions
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from bot.services.db import db

router = APIRouter()


class WalletConnectedEvent(BaseModel):
    tg_user_id: int
    chain:      str   # "evm" or "ton"
    address:    str


class DealFundedEvent(BaseModel):
    deal_id:    int
    tg_user_id: int
    tx_hash:    str
    on_chain_id: Optional[int] = None


class DealConfirmedEvent(BaseModel):
    deal_id:    int
    tg_user_id: int
    tx_hash:    str


class DealDisputeEvent(BaseModel):
    deal_id:    int
    tg_user_id: int
    reason:     Optional[str] = None


@router.post("/wallet-connected")
async def wallet_connected(event: WalletConnectedEvent):
    await db.update_user_wallet(event.tg_user_id, event.chain, event.address)
    return {"ok": True}


@router.post("/deal-funded")
async def deal_funded(event: DealFundedEvent):
    deal = await db.get_deal(event.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    if deal.buyer_tg_id and deal.buyer_tg_id != event.tg_user_id:
        raise HTTPException(403, "Not the buyer")

    import time
    guarantee_end = int(time.time()) + (deal.guarantee_hours or 24) * 3600
    await db.update_deal_status(event.deal_id, "funded")
    if event.on_chain_id:
        await db.update_deal_on_chain_id(event.deal_id, event.on_chain_id, guarantee_end)

    return {"ok": True, "status": "funded"}


@router.post("/deal-confirmed")
async def deal_confirmed(event: DealConfirmedEvent):
    deal = await db.get_deal(event.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    await db.update_deal_status(event.deal_id, "completed")
    return {"ok": True, "status": "completed"}


@router.post("/deal-disputed")
async def deal_disputed(event: DealDisputeEvent):
    deal = await db.get_deal(event.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    await db.update_deal_status(event.deal_id, "disputed")
    return {"ok": True, "status": "disputed"}
