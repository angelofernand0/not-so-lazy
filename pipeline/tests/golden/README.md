# Source-reviewed development pilot

`pilot.json` records five real filing pairs: AAPL, MSFT, HON, INTC and O.
It contains 262 ordered standalone risk headings across ten complete SEC HTML
documents, section start/end anchors, and explicit continuity relations. Sources
have original SEC URLs, report dates, accessions and raw SHA-256 checksums.
Four missing prior-year sources were added to `../fixtures/html/` as deterministic
gzip files; the other six reuse existing extraction fixtures.

These labels were selected by Codex by reading cached source HTML/text, without
copying pipeline factor IDs or alignment predictions. **They are agent-reviewed
development labels, not independently adjudicated human ground truth.** There
is no held-out test set yet. Do not infer S&P-wide accuracy from these five pairs.

The reference inventory is complete for standalone risk *starts*. Group titles,
preambles and nested subheadings are excluded. Exact factor body ends, change
types, economic significance and date masking correctness are not labeled here.
Split and merge relations explicitly retain continuity; they must not be turned
into artificial additions/removals to accommodate a one-to-one matcher. Intel's
foundry-strategy/14A continuity is unresolved and excluded from alignment and
added/removed metrics until independently adjudicated.

From `pipeline/`, with the pinned model already prepared:

```sh
uv run nsl evaluate --manifest tests/golden/pilot.json \
  --output ../docs/evaluation-pilot.json --report ../docs/EVALUATION-PILOT.md
```

Without model weights, append `--extraction-only`. This does not emit alignment
metrics. Use `--fixtures` to override the source root (default: the manifest's
grandparent directory). `DATA_DIR` controls the local model and parser-cache
location. Neither command needs a database, SEC identity or new EDGAR download.
The evaluator never downloads weights; `nsl model prepare` remains explicit.
`--fail-on-errors` writes results and then exits 1 if measured errors exist.

Before reporting any measurement, the evaluator verifies every raw checksum,
unique source boundary anchors, heading order, relation shape and exhaustive
one-relation-per-reference-factor coverage. Corrupt/missing sources or invalid
labels abort the run. Existing reports remain intact on input validation errors.

Report precision/recall with TP/FP/FN and denominators. All documents are counted,
including extraction flags. Conditional alignment excludes edges lacking detected
heading starts; always read it alongside end-to-end links and heading detection.
Zero denominators are `null`, not perfect scores. Changing labels changes the
recorded label hash; preserve the rationale and increment `label_version` when
adjudicating a label. Never change expected anchors just to fit parser output.

Next: independently review these labels and unresolved decisions, fix the errors
they expose, then add 25 diverse pairs and reserve a held-out subset before tuning.
Synthetic metric-accounting tests are explicitly labeled and are not validation
evidence.
