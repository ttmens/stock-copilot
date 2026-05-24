"""Dragon & Tiger list (龙虎榜) data provider — fetches from Eastmoney datacenter."""

import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class DragonTigerProvider:
    """Fetch dragon & tiger list data from Eastmoney.
    
    API endpoint: https://datacenter-web.eastmoney.com/api/data/v1/get
    Report: RPT_DAILYBILLBOARD_DETAILSNEW
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    def get_stock_dragon_tiger(
        self, 
        code: str, 
        days: int = 5
    ) -> Optional[dict]:
        """Get dragon & tiger list entries for a stock.
        
        Args:
            code: Stock code (e.g. "600519")
            days: Number of recent days to search
            
        Returns:
            Dict with code and entries list, or None if no data/error.
            Each entry has:
            - date: Trade date
            - reason: Reason for listing
            - net_buy: Net buy amount (positive = net inflow)
            - buy_amount: Total buy amount
            - sell_amount: Total sell amount
        """
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": str(days),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                if not data.get("success") or not data.get("result", {}).get("data"):
                    logger.debug(f"No dragon tiger data for {code}")
                    return None
                
                entries = []
                for item in data["result"]["data"]:
                    entry = {
                        "date": item.get("TRADE_DATE", ""),
                        "reason": item.get("EXPLAIN", ""),
                        "net_buy": float(item.get("NET_BUY_AMT", 0) or 0),
                        "buy_amount": float(item.get("TOTAL_BUY_AMT", 0) or 0),
                        "sell_amount": float(item.get("TOTAL_SELL_AMT", 0) or 0),
                    }
                    entries.append(entry)
                
                return {
                    "code": code,
                    "entries": entries
                }
                
        except Exception as e:
            logger.warning(f"Dragon tiger fetch failed for {code}: {e}")
            return None
