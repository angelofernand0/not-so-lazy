# Project status and next work

Snapshot: October 25, 2026. Complete source is on `docs-comprehensive-overview`,
including the Intel repair. All milestone PRs remain open; implementation is
not merged into `main`. The default branch is a project landing page linking to
this source. The hosted site is a development preview and may lag this branch.

## Review stack

Review in dependency order. Each branch builds on its predecessor; preserve
that order when merging or retargeting. Later PRs are not independent features
against `main`.

1. [PR #1 — Scaffold](https://github.com/angelofernand0/not-so-lazy/pull/1):
   `milestone-1-scaffold` → `main`; environment, pipeline/frontend skeleton and CI.
2. [PR #2 — EDGAR](https://github.com/angelofernand0/not-so-lazy/pull/2):
   `milestone-2-edgar` → `milestone-1-scaffold`; universe, discovery, pairing and cache.
3. [PR #3 — Extraction](https://github.com/angelofernand0/not-so-lazy/pull/3):
   `milestone-3-extraction` → `milestone-2-edgar`; cleaned blocks, candidate checks and review.
4. [PR #4 — Comparison](https://github.com/angelofernand0/not-so-lazy/pull/4):
   `milestone-4-comparison` → `milestone-3-extraction`; risk units, matching and masked diffs.
5. [PR #5 — Company pages](https://github.com/angelofernand0/not-so-lazy/pull/5):
   `milestone-5-company-pages` → `milestone-4-comparison`; searchable 20-company preview.
6. [PR #6 — Evaluation](https://github.com/angelofernand0/not-so-lazy/pull/6):
   `milestone-6-evaluation` → `milestone-5-company-pages`; frozen labels and measured baseline.
7. [PR #7 — Intel repair](https://github.com/angelofernand0/not-so-lazy/pull/7):
   `milestone-6b-intel` → `milestone-6-evaluation`; boundaries, segmentation and refreshed JSON.
8. Comprehensive documentation: `docs-comprehensive-overview` → `milestone-6b-intel`;
   quickstart, architecture, evidence, review map and contribution templates.

The latest code verification is in [Intel validation](INTEL-VALIDATION.md):
147 Python tests, six frontend tests, lint/type checks and static export passed.
[CI](https://github.com/angelofernand0/not-so-lazy/actions) also checks Postgres
migrations. Inspect current CI before merging; recorded test counts refer to
the verified revision.

## Current scope

Implemented: source caching, annual-pair discovery, Item 1A extraction and review
gates, segmentation, one-to-one matching, word/sentence diffs, static company
pages and offline pilot evaluation. The snapshot has 19 ready comparisons and
one held issuer (GEV) across 20 companies / 40 reports. The universe snapshot
contains 500 issuers, not 500 validated comparisons.

Not implemented: split/merge relations, computed language-change scores,
percentile leaderboard, optional AI summaries, full validated backfill,
automated R2 publishing and scheduled ingest/rebuild. Configuration placeholders
and empty UI states do not imply those features exist.

## Next: structural splits and merges

Five labeled continuity edges remain missing on the repaired pilot, with four
false additions and two false removals. One-to-one matching cannot represent
these structures. Intel's broad foundry-strategy/Intel-14A relation is unresolved;
do not turn it into ground truth by tuning thresholds.

Acceptance criteria:

- Introduce bounded one-to-many/many-to-one relations with source evidence and
  conservative review behavior for ambiguity.
- Preserve accepted matches, original text, offsets and hash validation; make
  structural changes distinguishable in exported data and the UI.
- Re-evaluate unchanged pilot labels and report per-case gains and regressions,
  including false structural matches. Do not change labels to fit predictions.
- Test Microsoft splits and Intel's technology/R&D merge with source fixtures.
  Bump affected stage/schema versions and regenerate downstream artifacts.

## Then: adjudicate and expand

- Independently review pilot labels and resolve/exclude ambiguity explicitly.
- Expand to 30 diverse pairs, including banks, spin-offs, amendments and fiscal transitions.
- Reserve an untouched subset before tuning. Measure boundary/start/continuity
  errors separately and add complete body-boundary checks.
- Investigate GEV's review flag from source evidence; retain the hold if unresolved.

## Then: scores and a defensible leaderboard

Implement the proposed metrics in [methodology](METHODOLOGY.md), test against
known changes, and publish definitions/sample counts alongside results. Gate a
full backfill on quality checks and benchmark review. Measure Brain correlation
on equivalent filing pairs and preprocessing separately from parser correctness;
no correlation result currently exists.

## Later: summaries and operations

Add optional cached summaries with exact source-quote verification and clear
failure behavior. Then implement shared-concurrency ingest, immutable publication,
rebuild triggers, observability and rollback. A working hosted preview does not
complete these production pipeline requirements.
