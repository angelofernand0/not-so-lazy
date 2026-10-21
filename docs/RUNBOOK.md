# Runbook

## Setup

From `pipeline/`: `uv sync --locked`, `uv run nsl doctor`, then
`uv run nsl init-db`. The latter applies Alembic migrations; it is safe to rerun.
`uv run alembic upgrade head` is the equivalent explicit migration command.
SQLite foreign keys are enabled for stage operations. CI also verifies migration
upgrade, schema/model agreement and downgrade on a disposable Postgres 17 service.

The root `.env` is loaded when commands run from `pipeline/`. Relative paths are
relative to the working directory, so use these documented working directories.
Never commit `.env`, databases or cached documents. The operator contact belongs
only in local environment or Actions secrets.

## Universe, discover and fetch

Set `SEC_USER_AGENT` to `NotSoLazy/0.1 your-real-contact@example.com`.
From `pipeline/`:

```sh
uv run nsl doctor --require-sec
uv run nsl universe refresh
uv run nsl discover --ticker AAPL
uv run nsl fetch --ticker AAPL
```

The snapshot is committed, so refresh is optional on a fresh clone. Refresh
fetches the constituent table and SEC ticker map, rejects any mismatching CIK,
and writes source/count/checksum metadata. Dotted share-class tickers normalize
to the SEC hyphen spelling for cross-checks, while the CSV keeps source spelling.
GOOG and GOOGL resolve to the same issuer and filing pair.

Omit `--ticker` for all issuers. `--since YYYY-MM-DD` filters current filing dates
for command output and fetch work; discovery still loads the history needed to
pair prior fiscal years. `discover --refresh` forces submissions JSON refresh;
otherwise it has a 24-hour TTL. History shards listed by SEC are all read and
cached. A company with no annual report reports `no_annual_filing`; a company
with one annual period has a `first_filing` pair. Bulk fetch skips undiscovered
issuers. Unexpected HTTP errors stop the command so a later retry can resume.

All workers on one host must use the same `DATA_DIR`: its `.sec-rate.sqlite`
file coordinates a capacity-one token bucket across clients, threads and processes
at <=8 requests/second. Do not run independent hosts against SEC simultaneously;
Milestone 8 workflows must share one concurrency group. Each retry consumes a
new token. HTTP 429 and 5xx and transient transport failures get at most five
retries, exponential delay and jitter; Retry-After is respected. Other HTTP
errors are not retried. Redirects are not followed with the contact header.

Raw primary documents use `raw/{cik}/{accession}.html` and have no expiration.
Metadata records source URL, original fetch time, size and SHA-256. Repeated
fetches rebuild DB metadata from cache without an HTTP request. Keep raw blobs
when rerunning stages or repairing a database.

## Offline cleaning and extraction

From `pipeline/`, after fetching:

```sh
uv run nsl clean --ticker AAPL
uv run nsl extract --ticker AAPL
uv run nsl extract --ticker MSFT --since 2026-01-01
```

Omit `--ticker` for all discovered active pairs. The current filing date controls
`--since`; the prior filing remains part of the comparison. These stages do not
construct an SEC client and need no SEC identity or API key. Missing or corrupt
inputs become review flags; they do not trigger a network download.

`cleaned_filings` points to `clean/{accession}/{version}-{source_hash}.json`.
Blocks preserve order, source index, page, tag, bold/italic/underline, list and
capitalization features, plus font size for distinguishing chapter headings from
small running footers. Inline-XBRL wrappers retain visible text; hidden content,
navigation tables, page markers and repeated headers/footers are removed.

`sections` stores the chosen text, counts, checksums, versions, quality flags and
candidate diagnostics. Full candidate text is retained under
`extraction-candidates/{accession}/{item}/{input_signature}.json`. The command
prints the candidate blob key and original SEC URL. The primary parser is
edgartools; the fallback operates independently over the cleaned blocks. Both
run on each new extraction. A parser error is logged by exception type and can
be recovered by the fallback.

The fallback accepts numbered/split headings and, where an item cross-reference
exists, a prominent bare chapter title. Bare end titles must be at the same
font level so a smaller risk-category heading does not terminate the section.
Sections use the configured Item 1B/1C/2 end boundaries for the MVP.

Input signatures include raw and cleaned hashes, both code versions, the installed
edgartools version, section rules and prior-year word count. Changes invalidate
the extraction cache. `--force` recomputes a stage explicitly. If a cleaned blob
is corrupt, run `clean --force` and then `extract`; never remove raw evidence.

Fewer than 2,000 words, a current/prior ratio outside 0.5–2, an implausible start,
Item 2 leakage, a short incorporated-reference body, a missing end boundary or
a clearly truncated sentence requires review. If candidate counts differ by
more than 10%, both are logged. A candidate passing checks wins over one failing;
if both plausible candidates disagree materially, the result remains in review.
A real large year-over-year change can legitimately trigger the ratio check.

## Amendments and review

10-K/A is recorded separately. For the selected annual periods, discovery probes
for a substantial Item 1A body before substituting an amendment. A short or
unterminated mention goes to review, never silently replacing the original. This
presence probe now uses the shared cleaner and boundary finder; full extraction
adds the size, leakage, plausibility and candidate-agreement checks.
Transition reports, missing fiscal years, irregular periods, changed fiscal year
ends and selected amendments carry explicit flags.

```sh
uv run nsl review list
uv run nsl review resolve REVIEW_ID --note "What was checked and corrected"
```

Resolution records a note and time; it does not override source evidence. Correct
the source/parser, increment its version and rerun the affected stage. A version change
reprobes amendments from cached HTML. Review entries are deduplicated by accession,
stage, version and reason; audit notes are retained. Recomputed extraction closes
flags that are no longer reproduced, recording an automatic resolution note.
If a resolved flag is reproduced later, it reopens with the prior resolution
noted. Resolving a review entry does not change the extracted source text or
silently remove its quality flags.

## Checks and frontend

Pipeline: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy notsolazy`, `uv run pytest`. Tests prohibit real socket connections.
Migration tests use disposable SQLite databases, never the operator's database.

From `web/`: `npm ci`, `npm run dev`. Production: `npm run build` creates
`web/out/`. Validate with `npm run lint` and `npm run typecheck`.

## Later milestones

Milestones 1–3 are implemented. Milestones 4–7 add risk-factor segmentation,
alignment, diffs, scores, company views and optional summaries. Milestone 8 enables
schedules, R2, rebuilding and deployment. No ingest cron runs yet.

Additional sections will use item-specific boundary/segmentation configuration.
The current amendment presence check only supports the MVP Risk Factors scope.
