"""Portfolio API router — positions and P&L tracking."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/positions", tags=["portfolio"])


class PositionCreate(BaseModel):
    code: str
    name: str = ""
    shares: float
    entry_price: float
    leverage: float = 1.0
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str = ""


class PositionUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    shares: float | None = None
    entry_price: float | None = None
    leverage: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str | None = None


@router.get("")
async def list_positions(open_only: bool = True):
    """List positions (open only or all)."""
    from src.portfolio.tracker import PositionTracker
    if open_only:
        return PositionTracker().summary()
    return {"positions": PositionTracker().list_positions(False)}


@router.post("")
async def create_position(body: PositionCreate):
    """Create new position."""
    from src.portfolio.tracker import PositionTracker
    return PositionTracker().create(
        body.code, body.name or body.code, body.shares, body.entry_price,
        body.leverage, body.stop_loss, body.take_profit, body.notes,
    )


@router.patch("/{position_id}")
async def update_position(position_id: int, body: PositionUpdate):
    """Update position fields."""
    from src.portfolio.tracker import PositionTracker
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return PositionTracker().update(position_id, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{position_id}")
async def delete_position(position_id: int):
    """Delete position."""
    from src.portfolio.tracker import PositionTracker
    if not PositionTracker().delete(position_id):
        raise HTTPException(status_code=404, detail="Position not found")
    return {"deleted": position_id}
