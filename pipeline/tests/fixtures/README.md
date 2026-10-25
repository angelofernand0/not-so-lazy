# Offline source fixtures

`aapl-annual-submissions.json` contains saved real SEC submissions rows for the
Apple 2025 and 2024 10-Ks; unrelated forms and history shards are omitted.

`extraction-cases.json` records the accession, CIK, source SEC URL, raw SHA-256,
fixture path and manually selected section start/end anchor snippets for 12 real
SEC HTML documents. `html/*.html.gz` contains the complete source bytes compressed
with deterministic gzip metadata. Decompressing must reproduce the recorded hash.

Coverage includes Apple (two years), Microsoft, Alphabet's shared-CIK annual,
Honeywell and Intel cross-reference/split-heading layouts, JPMorgan Chase (bank),
Realty Income (REIT), GE Vernova's first post-spin-off annual and its following
annual, Tesla's annual, and a Tesla 10-K/A adding Part III without Item 1A.
Recent sources also cover Item 1C end boundaries.

The GE Vernova prior annual contains a primary-parser truncation; the fallback
must reach the labeled end. Its following annual's large size change must remain
flagged for review. A flag is not itself evidence that the source is wrong.

This fixture set is not the 30-pair golden extraction/alignment evaluation planned
for Milestone 6 and establishes no S&P-wide accuracy rate. Synthetic edge cases
are labeled as such in the tests. All tests prohibit real socket connections.
To update sources, use the authenticated/rate-limited SEC CLI and preserve source
URLs, raw hashes and reviewed anchors. Never replace expected anchors merely to
match new parser output.
