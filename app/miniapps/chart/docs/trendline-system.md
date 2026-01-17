# Viewport-Aware Trendline System - Technical Specification

## Overview

A sophisticated, viewport-aware trendline system for K-line charts that automatically draws support/resistance channels based on visible data, with multi-scale trend detection.

---

## Architecture

### Data Flow

```
Viewport Change → Debounce (80ms) → makeParams() → ZigZag Segmentation → Channel Fitting → Rendering
```

### Components

| Component | Function |
|-----------|----------|
| `makeParams()` | Adaptive parameters based on visible bar count |
| `zigzag()` | Wave segmentation with ATR-adaptive reversal threshold |
| `buildSegments()` | Convert ZigZag points to trend segments |
| `fitChannelForSegment()` | Linear regression + quantile-based upper/lower rails |
| `detectRanges()` | Sliding window for horizontal consolidation boxes |
| Series Pools | Efficient rendering with fixed series count |

---

## Multi-Scale Design (v6)

### Dual ZigZag Thresholds

| Scale | Reversal (`rev`) | Purpose |
|-------|------------------|---------|
| **Short** | `max(k×ATR, 0.8%×price)`, k=1.2~2.0 | Swing channels (local structure) |
| **Long** | `max(k×ATR, 1.5%×price)`, k=2.6~3.8 | Main trend channel (skeleton) |

### Channel Types

1. **Swing Channels** (MAX=2): Short-scale, local wave structure
2. **Main Trend Channel** (1 only): Long-scale, overall trend direction
3. **Range Boxes** (MAX=1): Horizontal consolidation zones

---

## Key Fixes Applied

### v1→v2: Global Index Coordinates

**Problem**: Local slice indices caused line drift on pan/zoom.

```js
// Wrong: pivot.idx = i (local)
// Fixed: pivot.globalIdx = baseIdx + i (global)
```

### v2→v3: No Extrapolation by Default

**Problem**: Historical segment lines extended to viewport edge, looking ridiculous.

```js
// Only extrapolate lines ending in rightmost 15%
line.isActive = line.endGlobalIdx >= activeThreshold;
const lineEndLocal = line.isActive ? data.length - 1 : line.endGlobalIdx - baseIdx;
```

### v3→v4: ZigZag Segmentation

**Problem**: Pivot + slope-change method was unstable.

**Fix**: Replaced with proper ZigZag algorithm that only confirms turning points after sufficient price reversal.

### v4→v5: Horizontal Range Detection

**Problem**: ZigZag only detects trend waves, misses consolidation.

**Fix**: Added sliding window scan for flat zones (slope < 0.15×ATR, containment > 88%).

### v5→v6: Multi-Scale Channels

**Problem**: Single scale missed either local swings or overall trend.

**Fix**: Dual-scale ZigZag with separate series for swing and main trend channels.

### Regression Bug Fix

**Problem**: Wrong intercept formula broke Y-axis scale.

```js
// Wrong:
intercept: (sumY - sumX * (n * sumXY - sumX * sumY) / denom / n)

// Fixed:
const slope = (n * sumXY - sumX * sumY) / denom;
const intercept = (sumY - slope * sumX) / n;
```

### Log Scale Fix

**Problem**: Curved lines in linear mode.

**Fix**: `useLog = state.isLogScale` — follows chart's scale setting.

---

## Parameter Reference

### Adaptive Parameters by Visible Bar Count (N)

| N Range | `pivot_k` (short) | `pivot_k` (long) | Effect |
|---------|-------------------|------------------|--------|
| < 120 | 1.2 | 2.6 | More sensitive |
| 120-260 | 1.6 | 3.2 | Moderate |
| > 260 | 2.0 | 3.8 | Less sensitive |

### Containment Thresholds

| Channel Type | Containment | Description |
|--------------|-------------|-------------|
| Swing | 0.75 | 75% bars must fit within channel |
| Main Trend | 0.70 | More relaxed for long spans |
| Range Box | 0.88 | Strict for consolidation zones |

### Quantile-Based Rails

| Segment Length | Upper Quantile | Lower Quantile |
|----------------|----------------|----------------|
| < 30 bars | 0.90 | 0.10 |
| ≥ 30 bars | 0.95 | 0.05 |

---

## Rendering

### Series Allocation

| Layer | Series Count | Style |
|-------|--------------|-------|
| Swing Channels | 2 × 3 = 6 | Solid lines, width 2 |
| Main Trend | 1 × 3 = 3 | Dashed lines, distinct colors |
| Range Boxes | 1 × 3 = 3 | Dashed lines |

### Colors

```js
// Swing channels: use INDICATOR_COLORS
resistance: '#ff6b6b'  // Red
support: '#6bcb77'     // Green
trendLine: '#ffd93d'   // Yellow (mid)

// Main trend: distinct from swing
up: '#ff6b6b'
mid: '#ffd93d'
dn: '#6bcb77'
```

---

## Tuning Guide

### Too Many Fragmented Channels
→ Increase `kShort` (e.g., 1.2 → 1.5)

### Main Trend Not Detected
→ Decrease `MAIN_CONTAINMENT` (e.g., 0.70 → 0.65)

### Channels Too Wide/Narrow
→ Adjust quantile (0.95/0.05 → 0.92/0.08)

### Range Boxes Not Appearing
→ Decrease `RANGE_CONTAINMENT` (e.g., 0.88 → 0.85)

---

## API

```js
// Main entry point (called on viewport change)
export function updateDynamicAnalysis()

// Toggle visibility
export function togglePriceLines()

// Clear on timeframe change
export function resetTrendState()
```

---

## Files Modified

| File | Changes |
|------|---------|
| `js/analysis/trend.js` | Complete rewrite (v6) |
| `js/core/state.js` | Added `trendUpper2`, `trendLower2` series refs |
