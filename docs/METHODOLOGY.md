# Methodology

Status: ingestion, cleaning and extraction are implemented with segmentation, alignment and diff through Milestone 4.
No public comparisons or scores have been published. Full-universe validation
has not been performed.

Source: SEC EDGAR annual reports. Scope: current S&P 500, Item 1A Risk Factors,
latest versus prior fiscal year. Identify issuers by CIK and retain share-class
aliases. Pair by report date; flag transitions and missing annual periods.

Extraction runs edgartools and an independent cleaned-block boundary fallback
on cached HTML. Both candidates are retained with their versions and word counts.
The cleaner preserves visible text and formatting while removing hidden XBRL,
navigation and running page artifacts. Numbered, split and cross-referenced chapter
headings are supported. A candidate passing checks takes precedence; unresolved
large disagreement, suspect size ratios and boundary failures require review.
Twelve saved SEC documents have boundary regression checks, not a full-universe
accuracy evaluation. A smoke run of 18 annual reports retained one size-ratio flag
for review rather than declaring every extraction ready.

Segmentation uses standalone and inline styled risk headings with paragraph
fallback. Summary lists and introductions remain separate context. Alignment
runs exact normalized headings, unique reciprocal fuzzy headings (>=85), then
pinned MiniLM embedding cosine similarity with one-to-one Hungarian assignment
(>=0.80). Relative reorderings get a moved badge; simple insertion shifts do not.
Sentence and word diff operations retain offsets into original text on both sides.
Explicit fiscal-year/report-date rolls are masked, with their original spans
retained; historical years and unrelated numbers stay visible. Apple and Microsoft
pairs have generated offline demo artifacts. This is not a measured alignment
precision/recall result. Splits and merges can appear as additions/removals because
matching is one-to-one; paragraph fallback can also produce coarser units.

Headline measure: 1 minus cosine similarity of term-frequency vectors, with
standard English stop words removed. Also report Jaccard change, structural
counts, and share of inserted current words. Percentiles use fiscal years ending
in the same calendar year and are recalculated on publication. Position-only
changes do not affect language scores.

Optional AI summaries only receive changed factors. Verify quotes by normalized
exact substring matching against their source factor, dropping failed quotes.
No API key means the pipeline continues without summaries.

Research context: Cohen, Malloy & Nguyen, “Lazy Prices,” Journal of Finance (2020),
https://doi.org/10.1111/jofi.12885. This is context, never an investment signal.

Validation pending: golden set (30 real pairs), full-backfill extraction accuracy,
alignment precision/recall, and Spearman correlation against Brain BLMCF Risk
Factors similarity. No accuracy or correlation claim is made until measured.

Limits: formatting, split headings, amendments, fiscal-year changes, and imperfect
factor segmentation can affect results. A high change score does not indicate
whether a change is economically important.

Planned cadence: daily ingest, weekly publish on Sundays. The site reads static
published JSON; user requests never call EDGAR or an LLM.

Not investment advice. Data from SEC EDGAR. Not affiliated with the SEC.
