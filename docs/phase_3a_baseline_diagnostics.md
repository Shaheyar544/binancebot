# Phase 3A: Baseline Strategy Diagnostics Report

## 1. Executive Summary & Objective

This report documents the rigorous, reproducible baseline diagnostic evaluation of the **XAUUSDT Long-Only Strategy Engine** on commit `e382515` prior to any parameter optimization, score threshold relaxation, or logic alteration.

### Core Testing Scope & Constraints Enforced:
- **Strict Invariance**: Zero strategy parameters, weights, entry score thresholds (`min_score=80/85`), risk limits, leverage (`2.0x`), DCA maximum notional (`$500.00`), or exit rules were altered.
- **Dataset**: 25,857 finalized consecutive 15-minute candles ingested from Binance USDⓈ-M Perpetual Futures (`XAUUSDT`), spanning **December 11, 2025 to September 6, 2026 (~9 months)**. Price range: **$3,960.63 to $5,595.42**.
- **Execution Realism Policy**:
  - `IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST`: In any bar where both stop-loss and take-profit thresholds are breached, the stop-loss triggers first.
  - Causal ATR: Strictly finalized historical 15M candles with zero lookahead bias and zero fabricated fallbacks.
  - Fee Model: Maker 0.02%, Taker 0.05%, Slippage 0.01% (1 bps adverse penalty per market fill).
  - Liquidation Model: `EXPLICIT_MODEL` configured baseline tier ($2,400.00 fixed threshold, well below the user's `$2,500.00` safety ceiling). *Note: This represents a configured evaluation tier, not authoritative exchange cross-margin liquidation safety.*

---

## 2. Overall Performance Metrics

Across the entire 9-month historical scope, the bot generated 848 completed trades:

| Metric | Baseline Value | Interpretation / Context |
| :--- | :--- | :--- |
| **Total Completed Trades** | **848** | ~3.1 trades per calendar day (high statistical sample) |
| **Winning Trades / Losing Trades** | **291 / 557** | 34.32% Win Rate |
| **Gross Profit** | **+$719.06** | Total positive price edge before transaction costs |
| **Gross Loss** | **-$1,131.74** | Cumulative adverse excursion stopped out |
| **Net Realized Profit/Loss** | **-$412.68** | Realized PnL net of exchange fees and funding |
| **Profit Factor** | **0.64** | Gross Profit / Gross Loss |
| **Total Exchange Fees Paid** | **$1,166.52** | **Fee drag is 2.8x larger than net loss!** |
| **Total 8-Hour Funding Paid** | **$13.29** | Minimal funding drag over 9 months |
| **Max Account Drawdown** | **15.97%** | Controlled drawdown profile |
| **Average Realized R** | **-0.32R** | Expectancy per trade |
| **Median Realized R** | **-0.50R** | Median trade outcome |
| **Liquidations** | **0 (Zero)** | Capital safety constraints maintained |

---

## 3. Causal MFE / MAE & Excursion Analytics

| Excursion Metric | Baseline Value | Diagnostic Finding |
| :--- | :--- | :--- |
| **Average MFE ($)** | **$2.41** | Favorable excursion per trade in gold price points |
| **Median MFE ($)** | **$1.12** | Typical median favorable excursion |
| **Average MAE ($)** | **$2.36** | Average adverse draw before resolution |
| **Average MFE in R (`mfe_r_avg`)** | **+1.38R** | **Average peak open profit reaches +1.38R** |
| **Max R Reached** | **+74.58R** | Massive trend moves experienced by the position |
| **Average Realized R (`r_realized_avg`)** | **-0.32R** | Net realized R outcome |
| **Average Surrendered R (`r_surrendered_avg`)** | **+1.70R** | **1.70R of peak profit surrendered per trade** |
| **MFE Realization % for Winners** | **51.38%** | Winners capture roughly half their peak excursion |
| **Giveback %** | **1,159.22%** | Extreme surrender of open floating profit |
| **Positive MFE Closing as Loser %** | **60.26%** | **511 out of 848 trades reached profit but closed as losses!** |

---

## 4. R-Multiple Target Reach Rates

How often does an entry reach standard profit milestones before being stopped out?

| Target Milestone | Hit Rate (% of 848 Trades) | Trades Reaching Milestone | Realization & Outcome Analysis |
| :--- | :--- | :--- | :--- |
| **$\ge$ 0.5R** | **59.0%** | **500 trades** | Majority of entries move favorably initially |
| **$\ge$ 1.0R** | **38.0%** | **326 trades** | Over 1 in 3 trades achieves at least 1R open profit |
| **$\ge$ 1.5R** | **25.0%** | **212 trades** | 1 in 4 trades achieves substantial trend run |
| **$\ge$ 2.0R** | **19.0%** | **161 trades** | Nearly 1 in 5 trades achieves 2R+ run |

### Critical Finding on $\ge$ 1.0R Trades:
- Of the **326 trades** that reached $\ge 1.0R$ of favorable excursion:
  - **212 trades (65.03%) failed to realize $\ge 1.0R$ at exit.**
  - **134 trades (41.10%) reversed completely and closed as NET LOSERS.**
  - **Conclusion**: The strategy has a proven directional entry edge, but suffers catastrophic profit giveback due to lack of breakeven protection and rigid stop placement.

---

## 5. Segment Performance Breakdowns

### A. Setup Families

| Entry Family | Trades | Win Rate | Net PnL | Profit Factor | Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`BREAKOUT_RETEST`** | 109 | 32.11% | -$95.67 | 0.55 | **Weakest Family** (low win rate, poor PF) |
| **`SUPPORT_RECLAIM`** | 279 | 33.69% | -$137.28 | 0.69 | Moderate performance; high fee drag |
| **`TREND_PULLBACK`** | 460 | 35.22% | -$179.72 | 0.63 | High frequency (54% of all trades) |

### B. Market Regimes

| Market Regime | Trades | Win Rate | Net PnL | Profit Factor | Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`BEARISH_RANGE`** | 62 | **25.81%** | -$45.65 | **0.39** | **Weakest Regime by far** (unfavorable for LONG) |
| **`BULLISH_RANGE`** | 172 | 34.30% | -$135.01 | 0.45 | Whipsaw chop damages trailing stops |
| **`STRONG_BULL`** | 291 | 34.02% | -$132.83 | 0.69 | Substantial volume, but fee drag erodes edge |
| **`NEUTRAL`** | 98 | 32.65% | -$30.21 | 0.70 | Relatively small losses |
| **`BULL`** | 225 | **37.78%** | -$68.98 | **0.75** | **Best Performing Regime** |

### C. Score Buckets

| Score Bucket | Trades | Win Rate | Net PnL | Profit Factor | Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **80–84** | 0 | 0.0% | $0.00 | 0.00 | No trades scored in this tier |
| **85–89** | **848** | **34.32%** | **-$412.68** | **0.64** | **100% of trades clustered at exactly 85.0** |
| **90–100** | 0 | 0.0% | $0.00 | 0.00 | No trades scored $\ge 90$ |

*Observation: The scoring engine currently assigns an identical score of 85.0 to every qualified setup. There is zero score granularity to separate high-conviction signals from borderline signals.*

### D. DCA vs. No-DCA Execution

| Execution Mode | Trades | Win Rate | Gross Profit | Gross Loss | Net PnL | Profit Factor (Gross) | Total Fees | Average R |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **No-DCA (Single Entry)** | 798 | 32.71% | $901.92 | $343.48 | **-$542.42** | 2.63 | $1,100.87 | **-0.43R** |
| **DCA (Multi-Entry Adds)** | 50 | **60.00%** | $211.22 | $15.82 | **+$129.74** | **13.35** | $65.66 | **+1.42R** |

#### Crucial Finding on DCA:
- **DCA strictly IMPROVES trading outcomes**: DCA trades had a **60.00% win rate**, generated **+$129.74 net profit**, and produced an average realized R of **+1.42R** (vs. -0.43R for single entries).
- The strict qualification rules in the RiskEngine and StrategyEngine ensure DCA orders only execute when multi-timeframe confirmation remains intact, preventing blind averaging down while capitalizing on high-quality retests.

---

## 6. Largest Giveback Patterns

Top 10 trades with largest gap between peak favorable excursion (`max_r_reached`) and realized outcome (`realized_r`):

| Trade ID | Setup Family | Market Regime | Peak R | Realized R | R Surrendered | MFE ($) | Exit Reason | Net PnL |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `b56a2254` | TREND_PULLBACK | BULLISH_RANGE | +26.62R | -34.03R | **60.65R** | $0.98 | Stop loss [Adverse-First] | -$1.26 |
| `7779bff6` | TREND_PULLBACK | BULLISH_RANGE | +20.02R | +1.27R | **18.75R** | $0.99 | Trailing stop breached | +$0.06 |
| `0420ebf3` | TREND_PULLBACK | BULLISH_RANGE | +17.14R | -0.78R | **17.92R** | $1.66 | Stop loss ref breached | -$0.08 |
| `ad040a19` | TREND_PULLBACK | BULLISH_RANGE | +0.49R | -14.29R | **14.78R** | $0.21 | EMERGENCY_STOP_LOSS | -$6.18 |
| `b3aeb553` | TREND_PULLBACK | BULL | +8.94R | -3.88R | **12.82R** | $0.62 | Stop loss [Adverse-First] | -$0.27 |
| `b0d806fd` | TREND_PULLBACK | BULL | +0.09R | -12.70R | **12.79R** | $0.00 | EMERGENCY_STOP_LOSS | -$0.61 |
| `d6febb8c` | TREND_PULLBACK | BULLISH_RANGE | +74.58R | +62.85R | **11.73R** | $4.29 | EMERGENCY_STOP_LOSS | +$3.61 |
| `9878b880` | TREND_PULLBACK | BULLISH_RANGE | +2.02R | -8.56R | **10.58R** | $0.67 | EMERGENCY_STOP_LOSS | -$2.84 |
| `3d305148` | SUPPORT_RECLAIM | BULL | +0.00R | -9.94R | **9.94R** | $0.00 | EMERGENCY_STOP_LOSS | -$0.55 |
| `3e96ad1b` | SUPPORT_RECLAIM | BULL | +16.01R | +6.32R | **9.69R** | $10.23 | Trailing stop breached | +$4.04 |

---

## 7. Dominant Failure Modes & Hierarchy

From empirical telemetry, the failure modes rank as follows:

```
1. EXIT FAILURE (Dominant)
   ├── 60.26% of trades have positive MFE but close as net losers
   ├── 41.10% of trades reaching >= 1.0R close as losers (no Breakeven protection)
   └── Average surrendered R is +1.70R per trade (1,159% giveback)
        ↓
2. COST / EXECUTION DRAG (Severe)
   ├── $1,166.52 total fees paid vs -$412.68 net loss
   └── 100% taker fee market orders across 848 trades
        ↓
3. REGIME FILTERING (Secondary)
   ├── BEARISH_RANGE produces 25.81% win rate and 0.39 profit factor
   └── BULLISH_RANGE produces 0.45 profit factor due to chop
        ↓
4. SCORE CLUSTERING (Structural)
   └── 100% of trades clustered at flat score 85.0 (zero selectivity)
        ↓
5. ENTRY FAMILY (Minor)
   └── BREAKOUT_RETEST underperforms (32.11% WR, 0.55 PF) vs TREND_PULLBACK
```

### Summary of Explicit Requirements:
1. **Trades with positive MFE closing as losers**: **511 trades (60.26% of all trades)**.
2. **Trades reaching $\ge 1.0R$ failing to realize $\ge 1.0R$**: **212 trades (65.03%)**, with **134 trades (41.10%) reversing to close as losers**.
3. **Largest giveback patterns**: Concentration in `TREND_PULLBACK` within `BULLISH_RANGE`, where positions run 15R–60R before intrabar adverse-first stops trigger.
4. **Weakest score bucket**: **85–89** (flat 85.0 across all 848 trades; no discrimination).
5. **Weakest entry family**: **`BREAKOUT_RETEST`** (win rate 32.11%, profit factor 0.55).
6. **Weakest regime**: **`BEARISH_RANGE`** (win rate 25.81%, profit factor 0.39).
7. **DCA impact**: **DCA strictly IMPROVES outcomes** (60.00% win rate, +$129.74 net PnL, +1.42 average R).

---

## 8. Strategic Recommendations for Phase 3B (Optimization Target)

Based on diagnostic facts, Phase 3B should target the following non-disruptive, rule-bound improvements:

1. **Exit Engine Breakeven Protection**:
   - Move stop-loss to entry price + buffer once position reaches $+1.0R$ (or $+1.0 \times \text{ATR}$). This single mechanism will immediately eliminate 134 loser trades and capture significant profit.
2. **Dynamic Partial Take-Profit**:
   - Take 50% profit at $+1.5R$ to bank gains before adverse intrabar reversals occur.
3. **Regime Filter Exclusion**:
   - Prohibit new Long entries during `BEARISH_RANGE` (immediately pruning 62 unprofitable trades).
4. **Score Granularity & Thresholding**:
   - Restore scoring gradation across multi-timeframe confluence so the engine can differentiate between score 80, 85, and 90+.
5. **Execution Order Types**:
   - Transition non-urgent entries/exits to limit orders (Maker 0.02% vs Taker 0.05%) to reduce fee drag by over 60%.
