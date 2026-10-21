# Not So Lazy

**See what changed in every 10-K.** A free Risk Factors change tracker for students
and investment clubs, grounded in SEC EDGAR source filings.

## Status

Milestone 4: offline Risk Factors segmentation, three-pass year-over-year alignment,
and original-text span diffs on cached SEC extractions. Apple and Microsoft JSON
demos have been generated with the pinned local embedding model. Source checksums,
parser/matcher versions and review flags are preserved. Company pages, scores,
summaries, full backfill and deployment remain in later PRs; the frontend still
shows the pre-backfill empty state.

![Scaffold homepage preview](docs/scaffold-preview.png)

## Run locally

Requires Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and
Node.js 22 with npm. uv installs Python 3.12 as needed.

```sh
cp .env.example .env
cd pipeline
uv sync --locked
uv run nsl doctor
uv run nsl init-db
uv run alembic upgrade head
```

After setting your real SEC contact in `.env`, from `pipeline/`:

```sh
uv run nsl doctor --require-sec
uv run nsl discover --ticker AAPL
uv run nsl fetch --ticker AAPL
uv run nsl clean --ticker AAPL
uv run nsl extract --ticker AAPL
uv run nsl model prepare  # one explicit model download from Hugging Face
uv run nsl segment --ticker AAPL
uv run nsl align --ticker AAPL
uv run nsl diff --ticker AAPL
uv run nsl review list
```

The committed snapshot contains 503 tickers for 500 issuers, cross-checked against
SEC CIKs. `uv run nsl universe refresh` rebuilds it and refuses mismatches.
Omit `--ticker` to process the universe. `--since YYYY-MM-DD` selects pairs by
current filing date; it does not remove the older history needed for pairing.
Use `discover --refresh` to bypass the 24-hour submissions cache. Raw documents
are immutable in the cache and are never refetched by `fetch`.

In another terminal, from the repository root:

```sh
cd web
npm ci
npm run dev
```

Open http://localhost:3000. Frontend data lives in `web/public/site/`; no keys
or backend are needed to preview. Keys must never use a `NEXT_PUBLIC_` prefix.

Before any EDGAR request, set `SEC_USER_AGENT` in `.env` to
`NotSoLazy/0.1 your-real-contact@example.com`, then run
`uv run nsl doctor --require-sec` from `pipeline/`. Network stages refuse
missing identity, share a <=8 req/s throttle, and cache raw documents. Keep your
contact in `.env` or GitHub Actions secrets; never commit it. All concurrent
workers must share `DATA_DIR` so they share the rate-limit SQLite file.

Cleaning and extraction run entirely offline from cached HTML; no SEC identity
or LLM key is required for those stages. `extract` reads the versioned output of
`clean`, so run them in order. Use `--force` to recompute; otherwise unchanged
inputs reuse cached results. The JSON output includes local blob keys and SEC
source URLs so candidate texts and quality flags can be inspected.

The embedding model is pinned by commit and stored under `DATA_DIR/models/`.
`model prepare` is the only model-download command. Segment, align and diff are
offline and refuse missing/stale inputs or extraction flags. Alignment requires
the prepared model only when unmatched factors reach the semantic pass. A diff
command prints the versioned blob key; `data/diffs/{current_accession}.json` is
the convenient latest copy. Repeat the same stages with `--ticker MSFT` for the
second Milestone 4 demo. Re-run `clean` then `extract` when upgrading older caches.

## Layout

- `pipeline/notsolazy/`: SEC ingestion, HTML blocks, extraction, persistence, CLI and storage.
- `pipeline/migrations/`: versioned schema for companies, filings, cleaned blocks, sections and review.
- `pipeline/tests/`: offline tests, fixture and golden-set directories.
- `web/`: Next.js App Router, TypeScript, Tailwind and static export.
- `docs/`: decisions, methodology, operations and milestone plan.
- `.github/workflows/ci.yml`: offline Python tests, frontend build and Postgres migrations.

## Validate

```sh
cd pipeline
uv run ruff check .
uv run ruff format --check .
uv run mypy notsolazy
uv run pytest
```

From `web/` run `npm run lint`, `npm run typecheck`, and `npm run build`.

## Deployment plan

`npm run build` in `web/` writes `web/out/`. Vercel: set root directory `web`,
build command `npm run build`, output `out`. Cloudflare Pages: root `web`, build
`npm run build`, output `out`. No Next.js server, API routes or runtime secrets.
Publish precomputed JSON before rebuilding. R2 publishing, rebuild hooks, cron
and production deployment are Milestone 8 and are not configured yet.

Production state will use Postgres (Neon or Supabase) behind SQLAlchemy and R2
behind the blob interface. Summaries remain optional and provider-agnostic.

See [decisions](docs/DECISIONS.md), [runbook](docs/RUNBOOK.md),
[methodology](docs/METHODOLOGY.md), and [milestones](docs/MILESTONES.md).

Not investment advice. Data from SEC EDGAR. Not affiliated with the SEC.
