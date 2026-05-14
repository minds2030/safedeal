"""
api/main.py — FastAPI backend
Connects Mini App ↔ PostgreSQL ↔ Smart Contract
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from bot.services.db import db
from api.routes import deals, channels, webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    yield


app = FastAPI(title="SafeDeal API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deals.router,    prefix="/api/deals",    tags=["deals"])
app.include_router(channels.router, prefix="/api/channels", tags=["channels"])
app.include_router(webhook.router,  prefix="/api/webhook",  tags=["webhook"])


@app.get("/")
async def root():
    return {"status": "SafeDeal API running ✅"}

@app.get("/health")
async def health():
    return {"status": "ok"}
