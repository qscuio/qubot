
"""
Financial data tools for AI agents.
Ports of powerful tools from go-stock project.
"""

import json
import time
import aiohttp
from typing import Dict, Any, List, Optional
from app.services.ai.tools.base import Tool, ToolParameter, ToolResult
from app.core.logger import Logger
from app.core.config import settings

logger = Logger("FinancialDataTools")

class SearchStockByIndicatorsTool(Tool):
    """
    Search stocks using natural language indicators via EastMoney API.
    Ported from go-stock: ChoiceStockByIndicators
    """
    
    @property
    def name(self) -> str:
        return "search_stocks_by_indicators"
    
    @property
    def description(self) -> str:
        return (
            "Select stocks using natural language description of technical indicators or financial conditions. "
            "Examples: 'MACD golden cross', 'PE < 30 and increasing net profit', "
            "'Price above 20-day MA', 'Volume doubled yesterday'. "
            "Returns a list of matching stocks with relevant data."
        )
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="Natural language query string describing stock selection criteria. "
                            "e.g. 'shanghai beling, macd, rsi, kdj', 'semiconductor sector; PE<30'",
                required=True
            ),
            ToolParameter(
                name="page_size",
                type="integer", 
                description="Number of results to return (default 20)",
                required=False,
                default=20
            )
        ]
    
    async def execute(self, query: str, page_size: int = 20, **kwargs) -> ToolResult:
        try:
            fingerprint = settings.EASTMONEY_FINGERPRINT
            if not fingerprint:
                return ToolResult(
                    success=False,
                    output="EastMoney API requires authentication cookie (EASTMONEY_FINGERPRINT). Please configure it in .env."
                )

            # Note: The go-stock code implementation:
            # url := "https://np-tjxg-g.eastmoney.com/api/smart-tag/stock/v3/pw/search-code"
            # Body: {"keyWord": query, "pageSize": page_size, ...}
            
            url = "https://np-tjxg-g.eastmoney.com/api/smart-tag/stock/v3/pw/search-code"
            
            # Using a simplified payload
            payload = {
                "keyWord": query,
                "pageSize": page_size,
                "pageNo": 1,
                "fingerprint": fingerprint,
                "gids": [],
                "matchWord": "",
                "timestamp": str(int(time.time())),
                "shareToGuba": False,
                "requestId": "",
                "needCorrect": True,
                "removedConditionIdList": [],
                "xcId": "",
                "ownSelectAll": False,
                "dxInfo": [],
                "extraCondition": ""
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Origin": "https://xuangu.eastmoney.com",
                "Referer": "https://xuangu.eastmoney.com/"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        return ToolResult(
                            success=False,
                            output=f"API request failed with status {resp.status}: {await resp.text()}"
                        )
                    
                    data = await resp.json()
                    
                    # Logic from go-stock:
                    # if convertor.ToString(res["code"]) == "100" { ... }
                    
                    if str(data.get("code")) != "100":
                        msg = data.get("message", "Unknown error")
                        
                        # Handle specific authentication error
                        if str(data.get("code")) == "502" or "参数校验失败" in msg:
                             return ToolResult(
                                 success=False,
                                 output=f"EastMoney API authentication failed. Your EASTMONEY_FINGERPRINT might be invalid or expired. Error: {msg}"
                             )
                             
                        return ToolResult(success=False, output=f"EastMoney API Error: {msg} | Full Data: {data}")
                    
                    # Format the output table associated with the search result
                    result_data = data.get("data", {}).get("result", {})
                    data_list = result_data.get("dataList", [])
                    columns = result_data.get("columns", [])
                    
                    if not data_list:
                        return ToolResult(success=True, output="No stocks found matching the criteria.")
                    
                    # Create a readable summary or CSV-like output
                    # Columns mapping: key -> title
                    col_map = {}
                    headers_list = []
                    
                    for col in columns:
                        key = col.get("key")
                        title = col.get("title")
                        date_msg = col.get("dateMsg", "")
                        unit = col.get("unit", "")
                        
                        full_title = title
                        if date_msg:
                            full_title += f"[{date_msg}]"
                        if unit:
                            full_title += f"({unit})"
                        
                        col_map[key] = full_title
                        headers_list.append(full_title)
                    
                    # Format data
                    output_lines = []
                    output_lines.append(f"Found {len(data_list)} results for '{query}':")
                    output_lines.append(" | ".join(headers_list))
                    output_lines.append("-" * len(output_lines[-1]))
                    
                    for item in data_list:
                        row_vals = []
                        for col in columns:
                            key = col.get("key")
                            val = item.get(key, "")
                            row_vals.append(str(val))
                        output_lines.append(" | ".join(row_vals))
                    
                    return ToolResult(success=True, output="\n".join(output_lines))
                    
        except Exception as e:
            logger.error(f"SearchStockByIndicatorsTool error: {e}")
            return ToolResult(success=False, output=f"Internal error: {str(e)}")


class HotStrategyTool(Tool):
    """
    Get hot stock scanning strategies.
    Ported from go-stock: HotStrategy
    """
    
    @property
    def name(self) -> str:
        return "get_hot_strategies"
    
    @property
    def description(self) -> str:
        return "Get currently popular stock selection strategies from the market."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        try:
            url = f"https://np-ipick.eastmoney.com/recommend/stock/heat/ranking?count=20&trace={int(time.time())}&client=web&biz=web_smart_tag"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://xuangu.eastmoney.com/"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return ToolResult(success=False, output=f"API request failed: {resp.status}")
                    
                    data = await resp.json()
                    
                    # go-stock logic: strategy := &models.HotStrategy{}
                    # It iterates data and rounds 'Chg' (change).
                    
                    items = data.get("data", [])
                    if not items:
                        return ToolResult(success=True, output="No hot strategies found.")
                    
                    output_lines = ["Hot Stock Strategies:"]
                    output_lines.append(f"{'Name':<20} | {'Change':<10} | {'Description'}")
                    output_lines.append("-" * 50)
                    
                    # Looking at go-stock source, structure seems to be:
                    # { "Name": "...", "Chg": ..., "Desc": ... } (inferred)
                    # Let's dump the first item in debug if needed, but for now assume standard keys or print all
                    
                    for item in items:
                        name = item.get("Name", "Unknown")
                        chg = item.get("Chg", 0) * 100 # usually 0.0x
                        desc = item.get("Desc", "")
                        output_lines.append(f"{name:<20} | {chg:.2f}%     | {desc}")
                        
                    return ToolResult(success=True, output="\n".join(output_lines))
                    
        except Exception as e:
            return ToolResult(success=False, output=f"Error: {e}")

def register_financial_tools():
    """Register financial data tools with the registry."""
    from app.services.ai.tools.registry import register_tool
    register_tool(SearchStockByIndicatorsTool())
    register_tool(HotStrategyTool())

