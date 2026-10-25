# Architecture

The application is a batch parser plus a static reader. This document describes
the implemented development pipeline; production R2 publication, scheduling,
scores and summary generation remain planned.

## Ingestion and identity

`universe.py` loads the committed constituent snapshot and share-class aliases.
Companies are keyed by CIK, reports by accession, and annual pairs by report
date. `discover.py` records SEC submissions, history shards, amendments,
transition reports and pairing flags. `fetch.py` stores primary HTML and its
SHA-256, source URL, byte count and fetch time. Tickers are display/search aliases,
not filing identity.

`sec_client.py` validates the operator contact before requests and coordinates
an eight-request-per-second maximum through a shared local rate-limit database.
Raw cache entries are immutable. Discovery metadata has a refresh policy;
fetch does not redownload a cached primary document. Multi-host ingestion needs
future orchestration so independent rate limiters do not compete.

## Parsing and comparison

1. `clean.py` converts visible HTML into ordered blocks with source indices,
   page/formatting features and inline headings. Hidden XBRL, navigation and
   repeated running artifacts are removed.
2. `extract.py` compares edgartools with an independent block-boundary fallback.
   Both candidate texts and diagnostics remain available. Size, ratio, boundary
   and disagreement checks can hold the filing for review.
3. `segment.py` extracts heading/body units with original character offsets.
   Structured headings take precedence; repeated larger regular-weight headings
   are supported. Unstructured input can fall back to paragraphs. Introductions
   and summary lists remain context rather than standalone matched factors.
4. `align.py` accepts normalized exact headings, then reciprocal unique fuzzy
   matches, then pinned local MiniLM cosine/Hungarian assignment. Accepted units
   leave subsequent passes. The current matcher is one-to-one: splits and merges
   remain a measured limitation.
5. `diff.py` aligns sentences and word tokens, preserving each original side.
   Conservative fiscal-year/report-date masks are explicit spans, not destructive
   text edits. Relative order among matched factors determines moved badges.

`processing.py` and `comparison.py` coordinate persistent stages. Missing,
corrupt, stale or flagged upstream inputs prevent downstream results from being
treated as current. A parser/model/config change enters the stage signature;
rerun affected stages in order rather than reuse old JSON.

## Persistence and artifacts

`models.py` and Alembic migrations define companies/aliases, filings/pairs,
cleaned filings, sections, review entries, segmentation runs/risk factors,
alignment runs/edges and diff records. SQLite is the local default; Postgres
migrations run in CI. Database records reference hashes and blob keys.

`storage.py` defines the blob protocol and atomic, traversal-checked local store.
Only local storage is implemented. R2 environment fields reserve future
configuration; they do not provide a working publication backend today.

Important local artifact families under `DATA_DIR`:

- `raw/`: original primary HTML, retained when recomputing.
- `clean/`: versioned visible HTML blocks.
- `extraction-candidates/`: full candidate text and diagnostics.
- `diffs/`: immutable signature-addressed comparison JSON and a latest convenience copy.
- `models/`: explicitly downloaded, pinned embedding model.

Raw operational caches, SQLite databases, models, `.env` and credentials are
ignored by Git. Selected compressed public source fixtures belong in tests;
the published development snapshot belongs in `web/public/site/`.

## Static publication boundary

`preview.py` exports an explicit ticker selection only after checking current
stage signatures, payload checksum and complete diff-span coverage. Unready
filings produce review/status pages with source links. First filings and
missing pairs have separate states. The exporter manages files named in its
manifest and leaves unrelated files alone.

Next.js generates routes from the local snapshot. Each company page loads its
own same-origin diff payload; client validation checks SHA-256 and span
reconstruction before rendering. Offsets are half-open Unicode code points
from Python and must be converted for JavaScript's UTF-16 string indexing.
The browser has no database, SEC client, API keys or model runtime.

`npm run build` emits `web/out/`. A hosted development preview already exists;
this repository does not yet implement an automated ingest → R2 → rebuild →
production publication workflow. Hosting the reader and operating ingestion
are distinct steps.

## Evaluation boundary

`evaluate.py` runs the parser on compressed, hash-checked source fixtures without
the operational database or preview export. An independent source reader resolves
reference anchors and validates label coverage/relations. Full continuity
evaluation uses the local pinned encoder; extraction-only skips model use.
Neither mode downloads sources or weights silently.

The current five-pair pilot measures section endpoints, standalone risk starts
and labeled correspondence edges. It does not certify complete body endpoints,
economic importance or S&P-wide accuracy. Labels used to develop fixes need
independent human review and a held-out expansion before general accuracy claims.
