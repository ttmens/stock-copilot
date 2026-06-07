"""Watchlist API router."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    code: str
    name: str = ""


@router.get("")
async def list_watchlist():
    """List all watchlist items."""
    from src.watchlist.manager import WatchlistManager
    return {"stocks": WatchlistManager().list_dicts()}


@router.post("")
async def add_watchlist(body: WatchlistAdd):
    """Add stock to watchlist."""
    from src.watchlist.manager import WatchlistManager
    item = WatchlistManager().add(body.code.strip(), body.name.strip())
    return item


@router.delete("/{code}")
async def remove_watchlist(code: str):
    """Remove stock from watchlist."""
    from src.watchlist.manager import WatchlistManager
    if not WatchlistManager().remove(code):
        raise HTTPException(status_code=404, detail="Not in watchlist")
    return {"removed": code}


@router.patch("/{code}")
async def patch_watchlist(code: str, pinned: bool | None = None, name: str | None = None):
    """Update watchlist item (pin/unpin, rename)."""
    from src.watchlist.manager import WatchlistManager
    WatchlistManager().update(code, pinned=pinned, name=name)
    return {"code": code, "pinned": pinned, "name": name}


@router.post("/import-default")
async def import_default_watchlist():
    """Import default watchlist template."""
    from src.watchlist.manager import WatchlistManager
    n = WatchlistManager().import_default_template()
    return {"imported": n}
