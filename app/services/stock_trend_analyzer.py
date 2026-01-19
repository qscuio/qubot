# -*- coding: utf-8 -*-
"""
Stock Trend Analyzer - Ported from daily_stock_analysis
Core technical analysis logic including Trend, Bias, Volume, and Scoring.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """Trend Status Enum"""
    STRONG_BULL = "强势多头"      # MA5 > MA10 > MA20, spreading
    BULL = "多头排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱势多头"        # MA5 > MA10, but MA10 < MA20
    CONSOLIDATION = "盘整"        # Entangled
    WEAK_BEAR = "弱势空头"        # MA5 < MA10, but MA10 > MA20
    BEAR = "空头排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "强势空头"      # MA5 < MA10 < MA20, spreading


class VolumeStatus(Enum):
    """Volume Status Enum"""
    HEAVY_VOLUME_UP = "放量上涨"       # Price up, Vol up
    HEAVY_VOLUME_DOWN = "放量下跌"     # Price down, Vol up
    SHRINK_VOLUME_UP = "缩量上涨"      # Price up, Vol down
    SHRINK_VOLUME_DOWN = "缩量回调"    # Price down, Vol down (Good)
    NORMAL = "量能正常"


class BuySignal(Enum):
    """Buy Signal Enum"""
    STRONG_BUY = "强烈买入"       # High score
    BUY = "买入"                  # Good score
    HOLD = "持有"                 # Holding
    WAIT = "观望"                 # Wait
    SELL = "卖出"                 # Sell
    STRONG_SELL = "强烈卖出"      # Strong Sell


@dataclass
class TrendAnalysisResult:
    """Analysis Result Data Class"""
    code: str
    
    # Trend
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           
    trend_strength: float = 0.0      # 0-100
    
    # MA Data
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    current_price: float = 0.0
    
    # Bias (Change from MA5)
    bias_ma5: float = 0.0            # (Close - MA5) / MA5 * 100
    bias_ma10: float = 0.0
    bias_ma20: float = 0.0
    
    # Volume
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # Current Vol / 5D Avg Vol
    volume_trend: str = ""           
    
    # Support/Resistance
    support_ma5: bool = False        
    support_ma10: bool = False       
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    
    # Signal
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0            # 0-100
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'trend_status': self.trend_status.value,
            'ma_alignment': self.ma_alignment,
            'trend_strength': self.trend_strength,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
            'volume_status': self.volume_status.value,
            'volume_ratio_5d': self.volume_ratio_5d,
            'volume_trend': self.volume_trend,
            'support_ma5': self.support_ma5,
            'support_ma10': self.support_ma10,
            'buy_signal': self.buy_signal.value,
            'signal_score': self.signal_score,
            'signal_reasons': self.signal_reasons,
            'risk_factors': self.risk_factors,
        }


class StockTrendAnalyzer:
    """
    Stock Trend Analyzer
    
    Core Logic:
    1. Trend: MA5 > MA10 > MA20
    2. Bias: Avoid chasing highs (Bias MA5 > 5%)
    3. Volume: Prefer shrinking volume on pullback
    4. Buy Point: Support at MA5/MA10
    """
    
    # Config
    BIAS_THRESHOLD = 5.0        # Max Bias %
    VOLUME_SHRINK_RATIO = 0.7   
    VOLUME_HEAVY_RATIO = 1.5    
    MA_SUPPORT_TOLERANCE = 0.02  # 2%
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        """Analyze stock trend"""
        result = TrendAnalysisResult(code=code)
        
        if df is None or df.empty or len(df) < 20:
            result.risk_factors.append("Insufficient data")
            return result
        
        # Sort and Reset
        df = df.sort_values('date').reset_index(drop=True)
        
        # Calculate MAs
        df = self._calculate_mas(df)
        
        # Latest Data
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        result.ma5 = float(latest['MA5'])
        result.ma10 = float(latest['MA10'])
        result.ma20 = float(latest['MA20'])
        result.ma60 = float(latest.get('MA60', 0))
        
        # 1. Trend
        self._analyze_trend(df, result)
        
        # 2. Bias
        self._calculate_bias(result)
        
        # 3. Volume
        self._analyze_volume(df, result)
        
        # 4. Support/Resistance
        self._analyze_support_resistance(df, result)
        
        # 5. Signal Generation
        self._generate_signal(result)
        
        return result
    
    def _calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        else:
            df['MA60'] = df['MA20']
        return df
    
    def _analyze_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        
        if ma5 > ma10 > ma20:
            # Check spread expansion
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            # Avoid division by zero
            prev_ma20 = prev['MA20'] if prev['MA20'] > 0 else 1
            curr_ma20 = ma20 if ma20 > 0 else 1
            
            prev_spread = (prev['MA5'] - prev_ma20) / prev_ma20 * 100
            curr_spread = (ma5 - curr_ma20) / curr_ma20 * 100
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "强势多头排列，均线发散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = "多头排列 MA5>MA10>MA20"
                result.trend_strength = 75
                
        elif ma5 > ma10 and ma10 <= ma20:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = "弱势多头，MA5>MA10 但 MA10≤MA20"
            result.trend_strength = 55
            
        elif ma5 < ma10 < ma20:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_ma5 = prev['MA5'] if prev['MA5'] > 0 else 1
            curr_ma5 = ma5 if ma5 > 0 else 1
            
            prev_spread = (prev['MA20'] - prev_ma5) / prev_ma5 * 100
            curr_spread = (ma20 - curr_ma5) / curr_ma5 * 100
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "强势空头排列，均线发散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = "空头排列 MA5<MA10<MA20"
                result.trend_strength = 25
                
        elif ma5 < ma10 and ma10 >= ma20:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = "弱势空头，MA5<MA10 但 MA10≥MA20"
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均线缠绕，趋势不明"
            result.trend_strength = 50
    
    def _calculate_bias(self, result: TrendAnalysisResult) -> None:
        price = result.current_price
        if result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
            
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        if len(df) < 6:
            return
            
        latest = df.iloc[-1]
        # Use last 5 days excluding current to calculate avg? Or include?
        # External repo uses iloc[-6:-1] which is previous 5 days.
        vol_5d_avg = df['volume'].iloc[-6:-1].mean()
        
        if vol_5d_avg > 0:
            result.volume_ratio_5d = float(latest['volume']) / vol_5d_avg
            
        prev_close = df.iloc[-2]['close']
        price_change = (latest['close'] - prev_close) / prev_close * 100
        
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_UP
                result.volume_trend = "放量上涨，多头力量强劲"
            else:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_DOWN
                result.volume_trend = "放量下跌，注意风险"
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_UP
                result.volume_trend = "缩量上涨，上攻动能不足"
            else:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_DOWN
                result.volume_trend = "缩量回调，洗盘特征明显（好）"
        else:
            result.volume_status = VolumeStatus.NORMAL
            result.volume_trend = "量能正常"

    def _analyze_support_resistance(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        price = result.current_price
        
        # Support MA5
        if result.ma5 > 0:
            dist = abs(price - result.ma5) / result.ma5
            if dist <= self.MA_SUPPORT_TOLERANCE and price >= result.ma5:
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
        
        # Support MA10
        if result.ma10 > 0:
            dist = abs(price - result.ma10) / result.ma10
            if dist <= self.MA_SUPPORT_TOLERANCE and price >= result.ma10:
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
                    
        # MA20 Support
        if result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)
            
        # Resistance (Recent High)
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        score = 0
        reasons = []
        risks = []
        
        # 1. Trend Score (Max 40)
        trend_scores = {
            TrendStatus.STRONG_BULL: 40,
            TrendStatus.BULL: 35,
            TrendStatus.WEAK_BULL: 25,
            TrendStatus.CONSOLIDATION: 15,
            TrendStatus.WEAK_BEAR: 10,
            TrendStatus.BEAR: 5,
            TrendStatus.STRONG_BEAR: 0,
        }
        score += trend_scores.get(result.trend_status, 15)
        
        if result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            reasons.append(f"✅ {result.trend_status.value}，顺势做多")
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            risks.append(f"⚠️ {result.trend_status.value}，不宜做多")
            
        # 2. Bias Score (Max 30)
        bias = result.bias_ma5
        if bias < 0:
            if bias > -3:
                score += 30
                reasons.append(f"✅ 价格略低于MA5({bias:.1f}%)，回踩买点")
            elif bias > -5:
                score += 25
                reasons.append(f"✅ 价格回踩MA5({bias:.1f}%)，观察支撑")
            else:
                score += 10
                risks.append(f"⚠️ 乖离率过大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 28
            reasons.append(f"✅ 价格贴近MA5({bias:.1f}%)，介入好时机")
        elif bias < self.BIAS_THRESHOLD:
            score += 20
            reasons.append(f"⚡ 价格略高于MA5({bias:.1f}%)，可小仓介入")
        else:
            score += 5
            risks.append(f"❌ 乖离率过高({bias:.1f}%>5%)，严禁追高！")
            
        # 3. Volume Score (Max 20)
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 20,
            VolumeStatus.HEAVY_VOLUME_UP: 15,
            VolumeStatus.NORMAL: 12,
            VolumeStatus.SHRINK_VOLUME_UP: 8,
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,
        }
        score += volume_scores.get(result.volume_status, 10)
        
        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 缩量回调，主力洗盘")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意风险")
            
        # 4. Support Score (Max 10)
        if result.support_ma5:
            score += 5
            reasons.append("✅ MA5支撑有效")
        if result.support_ma10:
            score += 5
            reasons.append("✅ MA10支撑有效")
            
        # Finalize
        result.signal_score = score
        result.signal_reasons = reasons
        result.risk_factors = risks
        
        if score >= 80 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            result.buy_signal = BuySignal.STRONG_BUY
        elif score >= 65 and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL, TrendStatus.WEAK_BULL]:
            result.buy_signal = BuySignal.BUY
        elif score >= 50:
            result.buy_signal = BuySignal.HOLD
        elif score >= 35:
            result.buy_signal = BuySignal.WAIT
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            result.buy_signal = BuySignal.STRONG_SELL
        else:
            result.buy_signal = BuySignal.SELL

    def format_analysis(self, result: TrendAnalysisResult) -> str:
        """Format analysis as simple text"""
        lines = [
            f"📊 趋势判断: {result.trend_status.value} (强度:{result.trend_strength})",
            f"📈 评分: {result.signal_score}/100 ({result.buy_signal.value})",
            f"   MA5乖离: {result.bias_ma5:.1f}% | 量能: {result.volume_status.value}",
        ]
        if result.signal_reasons:
            lines.append(f"✅ {'; '.join(result.signal_reasons)}")
        if result.risk_factors:
            lines.append(f"⚠️ {'; '.join(result.risk_factors)}")
            
        return "\n".join(lines)
