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
capitalization features, the leading inline bold/italic heading when present,
plus font size for distinguishing chapter headings from
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

## Offline segmentation, alignment and diff

From `pipeline/`, after `clean` and `extract`:

```sh
uv run nsl model prepare
uv run nsl segment --ticker AAPL
uv run nsl align --ticker AAPL
uv run nsl diff --ticker AAPL
```

Repeat with `--ticker MSFT` for the second demo. `--ticker`, `--since`, `--item`
and `--force` work on these stages. `segment` processes both years; align/diff
process the pair. A first filing can be segmented but reports `first_filing`
for alignment/diff. Review-required extractions cannot proceed to comparison.
Resolving a review note alone does not override that gate.

`model prepare` downloads the public `sentence-transformers/all-MiniLM-L6-v2`
model at pinned revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` into
`DATA_DIR/models/`. It needs outbound Hugging Face access, no SEC contact or API
key. It fetches JSON/tokenizer files and safetensors weights, without custom remote
code. All other comparison commands load local files only. Missing weights yield
an explicit setup error; there is no silent network download or lexical substitute.
Linux dependencies use PyTorch's CPU-only wheel index.

`risk_factors` records group, heading, body, role, segmentation mode and half-open
character offsets into the selected Section text. Standalone category titles are
group metadata. Introductions and Summary of Risk Factors lists remain context,
excluded from risk matching. Missing heading formatting falls back to paragraphs.
The cleaner v2 also retains leading styled headings that share a paragraph with
body text, including an unstyled final period. Upgrading from v1 requires clean,
extract and segment again; raw downloads remain cached.

Matching passes remove accepted units before the next pass: normalized exact
heading, reciprocal unique fuzzy heading with token-set ratio >=85, and local
MiniLM cosine/Hungarian assignment at `ALIGNMENT_THRESHOLD` (default 0.80).
Dummy unmatched choices prevent rejected edges from displacing valid matches.
Duplicate headings use identical text to disambiguate where possible; unresolved
ones reach body embeddings. Moved badges compare relative order among matched
factors, so a new factor at the top does not mark every following risk moved.

`diff_records` points to immutable `diffs/{accession}/{item}/{signature}.json`;
`diffs/{accession}.json` is the convenient current copy. The payload includes
filing URLs, model/code versions, aligned factors, both original texts, sentence/
word span operations and explicit mask spans. Ranges are half-open Unicode code
point offsets (Python slicing); a future JS renderer must convert them rather
than treating them as UTF-16 offsets. Equal spans may have different original
text only where `trivial: true` represents a masked date roll. Pysbd splits
sentences, SequenceMatcher aligns them, and diff-match-patch compares word tokens
inside changed sentences. Each side reconstructs exactly from its operations.

Mask only the filing's own explicit fiscal year and `as of` report-date phrase.
Historical years, bare years and unrelated dates remain substantive. This is a
conservative mask; some harmless year changes will still appear as changes.

Stage signatures include upstream evidence hashes, dependency/code versions,
model revision, threshold and report dates. A changed segmentation invalidates
its pair's stored alignments and diff pointer. Downstream reads verify current
upstream signatures/checksums; stale or corrupt records require rerunning the
appropriate preceding stage. `--force` rebuilds its own stage. Extraction input
failures remain gated even if a historical diff blob still exists. The explicit
preview export below copies validated local artifacts into the website snapshot;
there is no automatic production publication workflow yet.

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

## Local company preview

From `pipeline/`, after the earlier stage commands:

```sh
uv run nsl preview --tickers AAPL,MSFT,GOOG,HON,INTC,JPM,O,GEV,TSLA,AMZN,NVDA,META,WMT,COST,V,DIS,JNJ,PG,HD,KO --output ../web/public/site
```

This command is fully offline and does not generate missing upstream stages. It
verifies current source/run signatures, the diff blob checksum and complete span
coverage before exporting. Failed quality/integrity checks produce a review page
with original SEC links and no stale counts/diff pointer. First filings and absent
pairs have separate states. The explicit ticker list avoids accidental full
backfill. Omitted prior snapshot companies/diffs are removed only if owned by the
exporter's manifest; unrelated files are left alone. Outputs are deterministic
for unchanged upstream records. This local snapshot command is not the future
production publish/R2 workflow.

The committed snapshot includes 20 companies and 40 reports. GE Vernova is in
review; the other 19 have comparisons. To refresh it, run discover/fetch, then
clean/extract/segment/align/diff per selected issuer and rerun preview. Never clear
quality flags merely to publish a comparison. A future build must read the new
snapshot before deployment. Original cache/DB/model files are never included.

From `web/`: `npm ci`, then `npm run dev`. `/` searches the preview by company,
ticker or known share-class alias. `/c/AAPL/` and `/c/MSFT/` show real comparisons;
`/c/GEV/` shows the held-for-review state. Unknown routes use the static 404 page.
The site verifies diff SHA-256 and Unicode offset coverage before rendering;
failed fetch/validation shows a retry action, never partial risk text.

Build with `npm run build`: Next.js emits all 20 company pages into `out/` using
local JSON. This build requires no EDGAR, embedding model or database connection.
`npm run test` runs Node 22 TypeScript helper and full-snapshot integrity tests.
The UI reads no server runtime API and carries no keys. Scores, percentile cards,
AI summary cards and pitch-deck copy belong to later milestones.

## Checks and frontend

Pipeline: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy notsolazy`, `uv run pytest`. Tests prohibit real socket connections.
Migration tests use disposable SQLite databases, never the operator's database.

From `web/`: `npm ci`, `npm run dev`. Production: `npm run build` creates
`web/out/`. Validate with `npm run lint`, `npm run typecheck` and `npm run test`.

## Recompute after the Intel layout fixes

Extraction and segmentation v3 invalidate older cached results. With the existing
raw cache, database, cleaned blocks and pinned model present, run from `pipeline/`:

```sh
uv run nsl extract
uv run nsl segment
uv run nsl align
uv run nsl diff
```

These commands are offline and operate only on discovered filing pairs already
in the database. Cleaner v2 blocks remain valid; run `clean` first if they are
absent. No `discover`/`fetch` or new model download is needed for this repair.
Then run the explicit 20-ticker `preview` command above and rebuild the static
site. Keep unresolved extraction reviews held; never clear GE Vernova's ratio
flag to make the export complete. Preview will reject stale stage signatures.

Reproduce the follow-up measurements without overwriting the historical baseline:

```sh
uv run nsl evaluate --manifest tests/golden/pilot.json \
  --output ../docs/evaluation-intel-fixed.json --report ../docs/EVALUATION-INTEL-FIXED.md
```

## Later milestones

Milestones 1–5 and the 6a/6b evaluation/layout repairs are implemented. Remaining
Milestone 6–7 work adds adjudicated validation, scores, full backfill and optional
summaries. Milestone 8 enables
schedules, R2 and automated rebuild/deployment. A hosted development preview
already exists, but no ingest cron or production publication workflow runs yet.

Additional sections will use item-specific boundary/segmentation configuration.
The current amendment presence check only supports the MVP Risk Factors scope.
