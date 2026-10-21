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
