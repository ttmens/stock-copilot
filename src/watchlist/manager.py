"""Watchlist manager — DB primary, JSON/YAML sync for legacy."""

import json
import logging
from pathlib import Path

from src.data.db_manager import SignalDB
from src.data.models import WatchlistItem

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_JSON_PATH = _PROJECT_ROOT / "config" / "watchlist.json"
_YAML_PATH = _PROJECT_ROOT / "config" / "watchlist.yaml"

DEFAULT_TEMPLATE = [
    ("600519", "贵州茅台"),
    ("000858", "五粮液"),
    ("000333", "美的集团"),
    ("601318", "中国平安"),
    ("600036", "招商银行"),
    ("300750", "宁德时代"),
    ("600276", "恒瑞医药"),
    ("002594", "比亚迪"),
    ("601012", "隆基绿能"),
    ("600900", "长江电力"),
]


class WatchlistManager:
    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()

    def _ensure_seeded(self) -> None:
        if self.db.list_watchlist():
            return
        # Seed from JSON if exists
        if _JSON_PATH.exists():
            try:
                data = json.loads(_JSON_PATH.read_text())
                codes = data if isinstance(data, list) else data.get("stocks", [])
                for code in codes:
                    meta = self.db.get_stock(code)
                    name = meta.get("name", code) if meta else code
                    self.db.add_watchlist(code, name)
                logger.info("Seeded watchlist from JSON: %d", len(codes))
                return
            except Exception as e:
                logger.warning("JSON seed failed: %s", e)
        # YAML fallback
        if _YAML_PATH.exists():
            import yaml
            try:
                with open(_YAML_PATH) as f:
                    data = yaml.safe_load(f) or {}
                for item in data.get("symbols", []):
                    self.db.add_watchlist(item["code"], item.get("name", item["code"]))
                return
            except Exception as e:
                logger.warning("YAML seed failed: %s", e)

    def list_items(self) -> list[WatchlistItem]:
        self._ensure_seeded()
        rows = self.db.list_watchlist()
        return [WatchlistItem(code=r["code"], name=r["name"]) for r in rows]

    def list_dicts(self) -> list[dict]:
        self._ensure_seeded()
        return self.db.list_watchlist()

    def add(self, code: str, name: str = "") -> dict:
        self._ensure_seeded()
        meta = self.db.get_stock(code)
        if not name and meta:
            name = meta.get("name", code)
        self.db.add_watchlist(code, name or code)
        self._sync_json()
        return {"code": code, "name": name or code}

    def remove(self, code: str) -> bool:
        ok = self.db.remove_watchlist(code)
        if ok:
            self._sync_json()
        return ok

    def update(self, code: str, pinned: bool | None = None, name: str | None = None) -> bool:
        ok = self.db.update_watchlist(code, pinned=pinned, name=name)
        if ok:
            self._sync_json()
        return ok

    def import_default_template(self) -> int:
        self._ensure_seeded()
        count = 0
        for code, name in DEFAULT_TEMPLATE:
            self.db.add_watchlist(code, name)
            count += 1
        self._sync_json()
        return count

    def _sync_json(self) -> None:
        """Keep config/watchlist.json in sync for legacy tools."""
        codes = [r["code"] for r in self.db.list_watchlist()]
        _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        _JSON_PATH.write_text(
            json.dumps({"stocks": codes, "version": 3, "source": "db"}, ensure_ascii=False, indent=2)
        )

    def codes(self) -> list[str]:
        return [i.code for i in self.list_items()]
