# Milestones — one reviewable PR each

1. Scaffold: Python/uv, Next.js static site, CI, environment, docs and setup tests.
2. EDGAR access/universe/discover/fetch: token bucket, retries, cache, committed
   cross-checked constituent snapshot, CIK identity, report-date pairing,
   transition/amendment handling; `nsl discover --ticker AAPL` demo.
3. Clean/extract: edgartools + fallback, quality flags, real tricky-filer fixtures.
4. Segment/align/diff: three-pass alignment and original-offset masked spans;
   real AAPL/MSFT JSON comparison demos.
5. Company frontend: search, company view and diff interactions for 20 tickers.
6. Score/leaderboard: full backfill, percentiles, golden evaluation and measured
   Brain correlation. No validation results may be invented.
7. Summaries: provider interface, optional Anthropic, verified quotes and cache,
   source-linked summary cards and pitch-deck copy.
8. Ship: daily/weekly Actions, R2 publication, rebuild trigger, deploy, public
   methodology/about, contact, screenshot and operational documentation.

Target: live with a backfill by late January 2027.
