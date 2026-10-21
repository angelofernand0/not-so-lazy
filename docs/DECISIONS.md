# Decisions

## Milestone 1 — Scaffold (2026-10-20)

- Preserve the brief’s Python 3.12 / uv and Next.js App Router / TypeScript /
  Tailwind / static-export stack. No runtime API or browser-side EDGAR calls.
- Start with an offline `nsl doctor` and `nsl init-db`. Validate SEC identity at
  every future network entry point; development setup needs no contact or keys.
- Keep `SECTION_ITEM` in config. Later stage APIs must accept item as a parameter.
- SQLite and local atomic blob writes support local development. SQLAlchemy,
  psycopg and Alembic provide the Postgres path. R2 is a later adapter to BlobStore.
- No stage table or fake stage command is added before its implementation. Alembic
  is wired to shared metadata; the first schema migration belongs to Milestone 2.
- Add extraction, NLP, embeddings, R2 and Anthropic dependencies when their stages
  arrive, rather than install large unused models in the scaffold.
- Never fabricate filing comparisons, S&P 500 membership, quotes or validation
  results. Publish explicit empty JSON and an honest pre-backfill UI for now.
- Search is visibly unavailable until the real company index arrives in Milestone 5.
- The frontend follows system light/dark preference, uses local system fonts,
  and avoids font downloads at build time. Explicit theme control can arrive with
  the company-page interaction work.
- Deployment stays in Milestone 8 per the brief. No daily/weekly workflow is
  scheduled before its stage commands exist; only CI runs now.
- `docs/METHODOLOGY.md` remains the public methodology source. The initial page is
  its concise scaffold counterpart; synchronize or automate rendering in Milestone 8.
- Repository starts private where possible. No open-source license is selected
  without a maintainer decision. Add owner/contact before launch.
- Use the supported Webpack backend for local dev and production builds;
  Turbopack’s CSS worker requires a local socket that this host denies.
  The application and static-export architecture are unchanged.

Validation: 14 offline pytest tests passed; Ruff lint/format, strict mypy,
ESLint, TypeScript, and the Webpack static export passed locally. Browser-checked
the exported homepage and methodology navigation. No filing ingestion or
production-data validation has been performed in this milestone.

## Milestone 2 — SEC access and filing pairs (2026-10-20)

- Use one httpx SEC entry point with a mandatory contact identity, an approved
  HTTPS host allowlist, retry/backoff policy and blob caching. Do not follow
  redirects with the contact header. Non-SEC Wikipedia requests omit the contact.
- Use a SQLite-backed capacity-one token bucket shared at `DATA_DIR/.sec-rate.sqlite`.
  This coordinates independent processes and threads on one host and prevents
  bursts. Multi-host scheduling remains serial and requires workflow concurrency
  controls in Milestone 8; independent rate-limit files are not a shared budget.
- Cache submissions and ticker JSON for 24 hours, with explicit refresh. Raw
  accession HTML never expires. Preserve original fetch metadata when rebuilding
  database records from existing cache. Failed HTTP responses are never cached.
- Commit the real 503-security/500-issuer snapshot and provenance/checksum.
  Refuse refresh on any CIK mismatch; never rewrite source CIKs silently.
  Normalize dot/hyphen symbols only for cross-checking and alias lookup.
- Key companies on CIK and retain ticker aliases in a separate table. Universe
  row versions include a content digest so snapshot changes can be traced.
- Discover all SEC history shards rather than assuming the recent window includes
  a prior annual period. Pair by report date, with transition/fiscal-year flags;
  missing prior reports remain first_filing and cannot enter a future leaderboard.
- Probe amendments only for the selected comparison periods. A substantial body
  with recognizable boundaries qualifies; short/ambiguous mentions require review.
  Store probe item/version and rerun when either changes. This is not the finished
  extraction algorithm or a claim of extraction accuracy.
- Implement `--since` as a current filing-date filter, not a history cutoff.
  Reruns update records by primary key and mark stale selected pairs superseded.
- Introduce an Alembic migration for companies, aliases, filings, pairs and review.
  `init-db` now uses migrations rather than metadata.create_all, avoiding duplicate
  table failures when later migrations are applied. SQLite enforces foreign keys.
- Keep PR 2 stacked on the unmerged Milestone 1 branch. No production deployment,
  full universe filing backfill, extraction, scores or summaries are claimed here.

Validation: 42 offline tests pass, with network sockets blocked. Ruff, strict
mypy and Alembic schema/model comparison pass. The live snapshot cross-check
passed for all 503 tickers. Live AAPL discovery selected report dates 2025-09-27
and 2024-09-28; both original HTML files were downloaded with checksums and sizes.
A repeat fetch passed with socket connections blocked. Postgres migration and
frontend checks run in the PR CI. Historical metadata flags remain on filing
records; the review queue focuses on selected periods and recent malformed rows.
