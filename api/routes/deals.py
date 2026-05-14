"""
api/routes/deals.py
Deal endpoints — Mini App fetches real deals from here
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from bot.services.db  import db
from bot.services.evm import evm_service
from bot.services.ton import ton_service
from config.settings  import settings, CHAINS

router = APIRouter()


# ── Response Models ───────────────────────────────────────────
class DealResponse(BaseModel):
    id:               int
    on_chain_id:      Optional[int]
    seller_username:  str
    buyer_username:   str
    seller_tg_id:     Optional[int]
    buyer_tg_id:      Optional[int]
    chain:            str
    token:            str
    amount:           float
    seller_gets:      float
    platform_fee:     float
    channel_fee:      float
    guarantee_hours:  int
    guarantee_end:    Optional[int]
    description:      str
    status:           str
    channel_id:       Optional[int]


class CreateDealOnChainRequest(BaseModel):
    deal_id:     int
    on_chain_id: int
    tx_hash:     str


class UpdateStatusRequest(BaseModel):
    deal_id:  int
    status:   str
    tx_hash:  Optional[str] = None
    tg_user_id: int


class DisputeResolveRequest(BaseModel):
    deal_id:      int
    winner:       str   # "seller" | "buyer" | "50"
    admin_tg_id:  int


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/", response_model=list[DealResponse])
async def get_deals(
    channel_id: Optional[int] = Query(None),
    tg_user_id: Optional[int] = Query(None),
    status:     Optional[str] = Query(None),
    limit:      int           = Query(20),
):
    """Get deals — filtered by channel, user, or status."""
    async with db.AsyncSessionLocal() as s:
        from sqlalchemy import select, or_
        from bot.services.db import Deal

        q = select(Deal)

        if channel_id:
            q = q.where(Deal.channel_id == channel_id)
        if tg_user_id:
            q = q.where(
                or_(Deal.seller_tg_id == tg_user_id,
                    Deal.buyer_tg_id  == tg_user_id)
            )
        if status:
            statuses = status.split(",")
            q = q.where(Deal.status.in_(statuses))

        q = q.order_by(Deal.created_at.desc()).limit(limit)
        result = await s.execute(q)
        deals  = result.scalars().all()

    return [DealResponse(
        id              = d.id,
        on_chain_id     = d.on_chain_id,
        seller_username = d.seller_username,
        buyer_username  = d.buyer_username,
        seller_tg_id    = d.seller_tg_id,
        buyer_tg_id     = d.buyer_tg_id,
        chain           = d.chain,
        token           = d.token,
        amount          = d.amount,
        seller_gets     = d.seller_gets,
        platform_fee    = d.platform_fee,
        channel_fee     = d.channel_fee,
        guarantee_hours = d.guarantee_hours or 24,
        guarantee_end   = d.guarantee_end,
        description     = d.description,
        status          = d.status,
        channel_id      = d.channel_id,
    ) for d in deals]


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(deal_id: int):
    deal = await db.get_deal(deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    return DealResponse(
        id              = deal.id,
        on_chain_id     = deal.on_chain_id,
        seller_username = deal.seller_username,
        buyer_username  = deal.buyer_username,
        seller_tg_id    = deal.seller_tg_id,
        buyer_tg_id     = deal.buyer_tg_id,
        chain           = deal.chain,
        token           = deal.token,
        amount          = deal.amount,
        seller_gets     = deal.seller_gets,
        platform_fee    = deal.platform_fee,
        channel_fee     = deal.channel_fee,
        guarantee_hours = deal.guarantee_hours or 24,
        guarantee_end   = deal.guarantee_end,
        description     = deal.description,
        status          = deal.status,
        channel_id      = deal.channel_id,
    )


@router.post("/confirm-onchain")
async def confirm_on_chain(req: CreateDealOnChainRequest):
    """Called by Mini App after createDeal() TX is confirmed."""
    import time
    deal = await db.get_deal(req.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")

    guarantee_end = int(time.time()) + (deal.guarantee_hours or 24) * 3600
    await db.update_deal_on_chain_id(req.deal_id, req.on_chain_id, guarantee_end)
    return {"ok": True, "on_chain_id": req.on_chain_id}


@router.post("/update-status")
async def update_status(req: UpdateStatusRequest):
    """Called by Mini App after fund/confirm/dispute TX."""
    deal = await db.get_deal(req.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")

    # Verify user is a party
    if req.tg_user_id not in (deal.seller_tg_id, deal.buyer_tg_id):
        raise HTTPException(403, "Not authorized")

    allowed = {
        "pending_payment": ["funded", "cancelled"],
        "funded":          ["delivered", "disputed"],
        "delivered":       ["completed", "disputed"],
        "disputed":        [],  # only admin can resolve
    }
    if req.status not in allowed.get(deal.status, []):
        raise HTTPException(400, f"Cannot change from {deal.status} to {req.status}")

    await db.update_deal_status(req.deal_id, req.status)
    return {"ok": True, "status": req.status}


@router.post("/resolve-dispute")
async def resolve_dispute(req: DisputeResolveRequest):
    """Channel admin resolves a dispute."""
    deal = await db.get_deal(req.deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")

    # Verify admin owns the channel
    channel = await db.get_channel(deal.channel_id)
    if not channel or channel.admin_tg_id != req.admin_tg_id:
        raise HTTPException(403, "Not channel admin")

    if deal.status != "disputed":
        raise HTTPException(400, "Deal is not disputed")

    # Map winner to seller_pct
    seller_pct = {"seller": 100, "buyer": 0, "50": 50}.get(req.winner, 100)

    try:
        if deal.chain == "ton":
            tx = await ton_service.resolve_dispute(deal, seller_pct)
        else:
            tx = await evm_service.resolve_dispute(deal, seller_pct)

        new_status = "completed" if seller_pct > 0 else "refunded"
        await db.update_deal_status(req.deal_id, new_status)
        return {"ok": True, "tx": tx, "status": new_status}
    except Exception as e:
        raise HTTPException(500, str(e))
