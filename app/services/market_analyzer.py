# -*- coding: utf-8 -*-
"""
Market Analyzer - Ported from daily_stock_analysis
Logic for analyzing market indices and sector performance.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import pandas as pd
from app.core.timezone import china_now

logger = logging.getLogger(__name__)


@dataclass
class MarketIndex:
    """Market Index Data"""
    code: str
    name: str
    current: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    amount: float = 0.0


@dataclass
class MarketOverview:
    """Market Overview Data"""
    date: str
    indices: List[MarketIndex] = field(default_factory=list)
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    total_amount: float = 0.0  # In Billion (Yi)
    
    top_sectors: List[Dict] = field(default_factory=list)
    bottom_sectors: List[Dict] = field(default_factory=list)


class MarketAnalyzerLogic:
    """
    Market Analyzer Logic
    
    Ported logic to fetch and organize market data.
    Note: Separation of Concerns - Data Fetching should be handled by the Service/Fetcher.
    This class organizes the data into the MarketOverview structure.
    """
    
    MAIN_INDICES = {
        'sh000001': '上证指数',
        'sz399001': '深证成指',
        'sz399006': '创业板指',
        'sh000688': '科创50',
    }

    def process_market_data(self, 
                          indices_df: pd.DataFrame, 
                          market_df: pd.DataFrame, 
                          sector_df: pd.DataFrame) -> MarketOverview:
        """
        Process raw dataframes into MarketOverview object.
        """
        today = china_now().strftime('%Y-%m-%d')
        overview = MarketOverview(date=today)
        
        # 1. Process Indices
        if indices_df is not None and not indices_df.empty:
            for code, name in self.MAIN_INDICES.items():
                row = indices_df[indices_df['代码'] == code]
                if row.empty:
                    # Try fuzzy match
                    row = indices_df[indices_df['代码'].str.contains(code)]
                
                if not row.empty:
                    row = row.iloc[0]
                    idx = MarketIndex(
                        code=code,
                        name=name,
                        current=float(row.get('最新价', 0)),
                        change=float(row.get('涨跌额', 0)),
                        change_pct=float(row.get('涨跌幅', 0)),
                        amount=float(row.get('成交额', 0))
                    )
                    overview.indices.append(idx)

        # 2. Process Market Stats (Up/Down)
        if market_df is not None and not market_df.empty:
            change_col = '涨跌幅'
            if change_col in market_df.columns:
                # Convert to numeric if needed
                market_df[change_col] = pd.to_numeric(market_df[change_col], errors='coerce')
                
                overview.up_count = len(market_df[market_df[change_col] > 0])
                overview.down_count = len(market_df[market_df[change_col] < 0])
                overview.flat_count = len(market_df[market_df[change_col] == 0])
                
                overview.limit_up_count = len(market_df[market_df[change_col] >= 9.9])
                overview.limit_down_count = len(market_df[market_df[change_col] <= -9.9])
                
            amount_col = '成交额'
            if amount_col in market_df.columns:
                 market_df[amount_col] = pd.to_numeric(market_df[amount_col], errors='coerce')
                 overview.total_amount = market_df[amount_col].sum() / 1e8

        # 3. Process Sectors
        if sector_df is not None and not sector_df.empty:
            change_col = '涨跌幅'
            if change_col in sector_df.columns:
                sector_df[change_col] = pd.to_numeric(sector_df[change_col], errors='coerce')
                sector_df = sector_df.dropna(subset=[change_col])
                
                top = sector_df.nlargest(5, change_col)
                overview.top_sectors = [
                    {'name': row['板块名称'], 'change_pct': row[change_col]}
                    for _, row in top.iterrows()
                ]
                
                bottom = sector_df.nsmallest(5, change_col)
                overview.bottom_sectors = [
                    {'name': row['板块名称'], 'change_pct': row[change_col]}
                    for _, row in bottom.iterrows()
                ]

        return overview

    def format_market_overview(self, overview: MarketOverview) -> str:
        """Format overview as text"""
        lines = [
            f"📅 <b>{overview.date} 市场复盘</b>",
            "",
            "<b>📊 主要指数</b>"
        ]
        for idx in overview.indices:
            icon = "🔴" if idx.change_pct > 0 else "🟢" if idx.change_pct < 0 else "⚪"
            lines.append(f"{icon} {idx.name}: {idx.current:.2f} ({idx.change_pct:+.2f}%)")
            
        lines.append("")
        lines.append("<b>📈 市场综合</b>")
        lines.append(f"🔺上涨: {overview.up_count} | 🔻下跌: {overview.down_count} | ⚪平盘: {overview.flat_count}")
        lines.append(f"🔥涨停: {overview.limit_up_count} | ❄️跌停: {overview.limit_down_count}")
        lines.append(f"💰两市成交: {overview.total_amount:.0f}亿")
        
        lines.append("")
        lines.append("<b>🚀 领涨板块</b>")
        sectors_up = "、".join([f"{s['name']}" for s in overview.top_sectors[:3]])
        lines.append(sectors_up)
        
        lines.append("")
        lines.append("<b>🌊 领跌板块</b>")
        sectors_down = "、".join([f"{s['name']}" for s in overview.bottom_sectors[:3]])
        lines.append(sectors_down)
        
        return "\n".join(lines)
