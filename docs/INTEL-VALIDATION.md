# Intel layout repair verification

Story: opening Intel's company page loads the precomputed, checksum-verified
diff JSON and renders complete risk factors from the two cached SEC reports.
The site has no runtime API, database connection or secrets.

## Pipeline and fixed references

- All 147 Python tests pass with socket connections blocked, including seven
  new layout regressions. Ruff lint/format and strict mypy pass.
- The same five pairs, raw source hashes and label hash were used before and
  after the repair. The original reference manifest and baseline JSON remain
  byte-for-byte unchanged. Labels still need independent human adjudication.
- Section endpoints improve from 9/10 to 10/10. Risk starts improve from 262
  true / 320 extra / 0 missed to 262 true / 0 extra / 0 missed. False continuity
  links decrease from 113 to zero; five labeled continuity edges remain missing.
- The real Intel sources produce exactly 24 prior and 22 current risk units,
  rather than 200 and 166 paragraph-sized units. Tests verify bodies spanning
  multiple paragraphs, source offsets and the retained introduction.
- The primary prior extraction's following chapter remains available in its
  diagnostics, flagged `contains_following_section`; the bounded fallback ends
  at the reviewed endpoint before Sales and Marketing.

See [full measurements](EVALUATION-INTEL-FIXED.md) and
[machine-readable evidence](evaluation-intel-fixed.json). These are development
measurements on deliberately selected examples, not S&P-wide estimates.

## Preview data and frontend

- Reprocessed all 40 cached annual reports and rebuilt the explicit 20-company
  preview with socket connections blocked. The original checkout was not changed.
- Nineteen comparisons remain ready; GE Vernova remains held for extraction
  review. No unresolved flag was cleared to produce the snapshot.
- The other 18 ready comparisons retain their risk counts, reference headings
  and matching classifications. Regenerating source text also refreshes whitespace,
  list markers and previously retained Microsoft Item 1A footer strings, so
  associated IDs, original offsets, payload signatures and checksums are rebuilt.
- All six frontend tests pass, including SHA-256 checks and reconstruction of
  every prior/current diff span across the real snapshot. ESLint, TypeScript and
  the production static export pass; all 20 company routes are generated.

## Browser-to-data flow

- Served `web/out` on loopback with Python's static HTTP server. Both
  `GET /c/INTC/` and `GET /site/diffs/0000050863-26-000011.json` returned 200.
- Intel's page rendered the two original SEC source links and FY 2024/2025 dates.
  The client passed its payload checksum and span validation and displayed
  “Showing 26 of 26 risks” with full bodies under the risk headings.
- The 26 comparison cards comprise 22 current units plus four unmatched prior
  units. They are not 26 distinct risks in either source filing. The visible
  counts are 2 added, 4 removed and 20 modified under the existing matcher.
- Collapse all changes to Expand all and leaves the complete heading inventory
  available. This checks the reading interaction as well as static HTML output.

## Remaining limits

One-to-one alignment still presents split/merged risks as unmatched. Intel's
technology-development factor is still shown as removed although the pilot
labels it as merged into the current R&D/manufacturing factor. The continuity
between the broad prior foundry strategy and the current Intel 14A factor remains
unresolved in the reference labels. These matching limits are separate from the
fixed extraction and segmentation failures; do not interpret the display counts
as fully adjudicated additions/removals or economic significance.
