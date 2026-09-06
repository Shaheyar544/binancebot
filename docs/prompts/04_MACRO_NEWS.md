# Prompt 04 — Macro, News and Event Lock

Implement macro/news intelligence as a separate non-execution layer.

Prefer official Federal Reserve, BLS, BEA and U.S. Treasury sources. Use reputable financial reporting for context. Store source, timestamps, freshness and classification.

Track high-impact U.S. events including FOMC, CPI, NFP, PPI, PCE, GDP, Retail Sales, ISM, JOLTS, ADP, Jobless Claims, Consumer Confidence, University of Michigan inflation expectations, Treasury announcements and major geopolitical events.

Enforce: no NEW trades from 24 hours before a high-impact event until 24 hours after it. After that use POST_NEWS_REASSESSMENT and require normal technical/risk gates.

Existing positions are not automatically closed because news arrives or P&L is negative. AI may summarize and score macro context but cannot trade or override RiskEngine.
