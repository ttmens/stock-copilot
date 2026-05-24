
"""Force-run analysis on non-trading day to generate demo data."""
import sys
import asyncio
sys.path.insert(0, "/home/ubuntu/repos/stock-copilot")

from dotenv import load_dotenv
load_dotenv()

from src.data.fetcher import DataFetcher, fetch_all
from src.data.models import ReportType, Report, StockAnalysis, MarketOverview, WatchlistItem
from src.data.calendar import is_trading_day
from src.orchestrator.pipeline import _analyze_and_fuse, _load_watchlist
from src.reports.generator import generate_report
from src.site.generator import generate_site
from datetime import date, datetime

async def force_analyze():
    print("=== 强制分析（跳过交易日检查）===")
    
    # Load watchlist
    watchlist = _load_watchlist()
    print(f"自选股: {len(watchlist)} 只")
    
    # Fetch data
    fetcher = DataFetcher()
    snapshots, failed = await fetch_all(watchlist)
    print(f"采集: {len(snapshots)} 成功, {len(failed)} 失败")
    
    # For each snapshot, print key data
    for snap in snapshots:
        bars = snap.bars or []
        print(f"  {snap.code} {snap.name}: {len(bars)}根K线, 最新收盘={bars[-1].close if bars else 'N/A'}")
        if snap.valuation:
            v = snap.valuation
            print(f"    PE={v.pe_ttm}, PB={v.pb}, 市值={v.mcap/1e8:.0f}亿")
    
    # Run agents + fuse
    analyses, fused = await _analyze_and_fuse(snapshots)
    print(f"分析+融合: {len(analyses)} 完成")
    
    # Print fusion results
    for code, rec in fused.items():
        print(f"  {code}: score={rec.final_score:+.2f} signal={rec.final_signal} conf={rec.llm_confidence:.2f}")
        if rec.ma_alignment:
            print(f"    MA={rec.ma_alignment} 动量5d={rec.momentum_5d}% 量比={rec.volume_ratio}")
    
    # Build report
    report = generate_report(analyses, ReportType.PRE, None, failed)
    print(f"报告: {report.file_path}")
    
    # Generate site
    site_path = generate_site(report)
    print(f"站点: {site_path}")
    
    return report

report = asyncio.run(force_analyze())
print(f"\n✅ 分析完成: {report.file_path}")
