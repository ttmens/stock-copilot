"""Single-user position CRUD and rule checks — Phase G9."""

import logging
from datetime import date

from src.data.db_manager import SignalDB
from src.monitoring.alerts import AlertDispatcher

logger = logging.getLogger(__name__)


class PositionTracker:
    def __init__(self, db: SignalDB | None = None, user_id: str = "default"):
        self.db = db or SignalDB()
        self.user_id = user_id
        self.alerts = AlertDispatcher(self.db)

    def list_positions(self, open_only: bool = True) -> list[dict]:
        return self.db.get_positions(self.user_id, open_only=open_only)

    def create(self, code: str, name: str, shares: float, entry_price: float,
               leverage: float = 1.0, stop_loss: float | None = None,
               take_profit: float | None = None, notes: str = "") -> dict:
        pid = self.db.save_position(
            self.user_id, code, name, shares, entry_price,
            leverage, stop_loss, take_profit, notes,
        )
        return {"id": pid, "code": code, "name": name}

    def update(self, position_id: int, **kwargs) -> dict:
        pos_list = self.db.get_positions(self.user_id, open_only=False)
        pos = next((p for p in pos_list if p["id"] == position_id), None)
        if not pos:
            raise ValueError(f"Position {position_id} not found")
        self.db.save_position(
            self.user_id,
            kwargs.get("code", pos["code"]),
            kwargs.get("name", pos["name"]),
            kwargs.get("shares", pos["shares"]),
            kwargs.get("entry_price", pos["entry_price"]),
            kwargs.get("leverage", pos["leverage"]),
            kwargs.get("stop_loss", pos.get("stop_loss")),
            kwargs.get("take_profit", pos.get("take_profit")),
            kwargs.get("notes", pos.get("notes", "")),
            position_id=position_id,
        )
        return {"id": position_id, "updated": True}

    def close(self, position_id: int) -> bool:
        return self.db.close_position(position_id, self.user_id)

    def delete(self, position_id: int) -> bool:
        return self.db.delete_position(position_id, self.user_id)

    def check_rules(self) -> int:
        """Check stop-loss / take-profit against current prices."""
        triggered = 0
        for pos in self.list_positions():
            price = self._current_price(pos["code"])
            if price is None:
                continue
            entry = pos["entry_price"]
            pnl_pct = (price - entry) / entry * 100

            if pos.get("stop_loss") and price <= pos["stop_loss"]:
                self.alerts.dispatch(
                    pos["code"], pos["name"], "stop_loss",
                    f"触发止损：现价 {price:.2f} ≤ 止损 {pos['stop_loss']:.2f}",
                    severity="action",
                )
                triggered += 1
            elif pos.get("take_profit") and price >= pos["take_profit"]:
                self.alerts.dispatch(
                    pos["code"], pos["name"], "take_profit",
                    f"触发止盈：现价 {price:.2f} ≥ 止盈 {pos['take_profit']:.2f}",
                    severity="watch",
                )
                triggered += 1
            elif pnl_pct < -5:
                self.alerts.dispatch(
                    pos["code"], pos["name"], "drawdown",
                    f"浮亏 {pnl_pct:.1f}% 超过 -5%",
                    severity="watch",
                )
                triggered += 1
        return triggered

    def _current_price(self, code: str) -> float | None:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code]
            if not row.empty:
                return float(row.iloc[0].get("最新价", 0))
        except Exception:
            pass
        return None

    def summary(self) -> dict:
        positions = self.list_positions()
        return {
            "user_id": self.user_id,
            "open_count": len(positions),
            "positions": positions,
            "trade_date": date.today().isoformat(),
        }
