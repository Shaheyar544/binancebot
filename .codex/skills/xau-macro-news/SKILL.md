---
name: xau-macro-news
description: Build source-attributed macro/news intelligence and enforce the 24-hour high-impact event lock without allowing AI to trade.
---
# XAU Macro and News

Official sources first: Federal Reserve, BLS, BEA, U.S. Treasury. Context: Reuters, Bloomberg, Financial Times. Rumors/social posts are not facts.

Every item is FACT, EXPECTATION, ANALYSIS, or AI_INTERPRETATION and stores source, URL/reference, publication time, retrieval time, event time, freshness and confidence.

High-impact lock: event_time - 24h through event_time + 24h => no new trades. Then POST_NEWS_REASSESSMENT; resume only after normal technical/risk gates pass.

Existing positions are not auto-closed merely because news arrives or P&L is negative.

AI may summarize and score macro context but cannot place orders, override RiskEngine, or change user capital/leverage/liquidation limits.
