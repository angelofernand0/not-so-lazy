# Filing comparison development evaluation

Agent-reviewed pilot labels; independent human adjudication is pending. This is a development baseline, not a held-out benchmark or S&P 500 accuracy claim.

Sources: 5 filing pairs / 10 cached SEC documents. All raw SHA-256 checks and reference anchors were verified before evaluation.

- Section boundary anchors pass: 10/10.
- Documents with extraction flags: 0 (included in denominators).
- Risk heading starts: precision 100.0%; recall 100.0%; TP/FP/FN 262/0/0.
- Continuity links, end to end: precision 100.0%; recall 96.1%; TP/FP/FN 123/0/5.
- Continuity links, conditional on detected headings: precision 100.0%; recall 96.1%; TP/FP/FN 123/0/5.
- Added standalone factors: precision 50.0%; recall 100.0%; TP/FP/FN 4/4/0.
- Removed standalone factors: precision 66.7%; recall 100.0%; TP/FP/FN 4/2/0.
- Unresolved reference endpoints excluded: 2.

## Definitions and limits

- section_boundaries: Start anchor in first 1000 normalized characters AND exact normalized end-anchor suffix; all filings included, even flagged ones. Not full text accuracy.
- heading_starts: One distinct predicted risk unit must start with each reference heading. Does not measure exact body-end segmentation.
- links_end_to_end: Micro precision/recall of labeled continuity edges including segmentation misses and split/merge edges. Unmapped units count as false predictions.
- links_on_detected_headings: Conditional micro precision/recall restricted to links whose two reference heading starts were detected. Read alongside heading recall and end-to-end links.
- added_removed: Standalone factor additions/removals, not new/deleted topics. Split/merge continuations are not additions/removals. Unresolved reference endpoints excluded.
- undefined: A zero denominator produces null, never a fabricated perfect score.
- Five deliberately selected pairs; not representative of the S&P 500.
- Heading-start detection is measured; exact factor body-end accuracy and change-type correctness are not measured.
- Split/merge groups express all labeled continuity edges; one-to-one alignment cannot recover every edge.
- Unresolved continuity groups are reported and excluded from alignment and added/removed metrics.

## Versions

```json
{
  "cleaner": "clean-v2",
  "extractor": "extract-v3",
  "segmenter": "segment-v3",
  "aligner": "align-v1",
  "model_revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
  "semantic_threshold": 0.8,
  "fuzzy_threshold": 85
}
```

## AAPL

Retail-store standalone risk is removed as a factor; overlapping retail discussion elsewhere does not constitute a retained standalone factor. Quarterly sales becomes sales/gross-margin volatility; ESG becomes stakeholder expectations.

- [prior source](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 28/0/0; flags: none.
- [current source](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 27/0/0; flags: none.

### Errors

No errors under the measured checks.

## MSFT

Bold italic competition/security/abuse subheads stay inside parent risks. Plain bold inline headings with punctuation in a following span are separate risks. Cloud/AI execution, infrastructure, and supply/quality risks are split across the current filing.

- [prior source](https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 23/0/0; flags: none.
- [current source](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 26/0/0; flags: none.

### Errors

- {"category": "missing_link", "prior": "p02", "current": "c02", "prior_heading": "Our focus on cloud-based and AI services presents execution and competitive risks.", "current_heading": "Our cloud and AI strategy requires substantial investments and depends on evolving customer demand, technological developments, competitive dynamics, and regulatory conditions, any of which could adversely affect our business, financial condition, and results of operations."}
- {"category": "missing_link", "prior": "p02", "current": "c03", "prior_heading": "Our focus on cloud-based and AI services presents execution and competitive risks.", "current_heading": "Our success depends on our ability to develop, deliver, and maintain competitive cloud-based and AI products and services that achieve broad customer adoption and sustainable revenue growth."}
- {"category": "missing_link", "prior": "p11", "current": "c14", "prior_heading": "We may have excessive outages, data losses, and disruptions of our online services if we fail to maintain an adequate operations infrastructure.", "current_heading": "We may experience outages, disruptions, or capacity constraints if we fail to maintain and operate adequate infrastructure or secure the resources necessary to support it."}
- {"category": "missing_link", "prior": "p12", "current": "c15", "prior_heading": "We may experience supply or quality problems.", "current_heading": "We may experience other quality problems."}
- {"category": "false_added", "factor": "c02", "heading": "Our cloud and AI strategy requires substantial investments and depends on evolving customer demand, technological developments, competitive dynamics, and regulatory conditions, any of which could adversely affect our business, financial condition, and results of operations."}
- {"category": "false_added", "factor": "c03", "heading": "Our success depends on our ability to develop, deliver, and maintain competitive cloud-based and AI products and services that achieve broad customer adoption and sustainable revenue growth."}
- {"category": "false_added", "factor": "c14", "heading": "We may experience outages, disruptions, or capacity constraints if we fail to maintain and operate adequate infrastructure or secure the resources necessary to support it."}
- {"category": "false_added", "factor": "c15", "heading": "We may experience other quality problems."}
- {"category": "false_removed", "factor": "p02", "heading": "Our focus on cloud-based and AI services presents execution and competitive risks."}

## HON

Standalone risks retain order and continuity despite changes to separation plans, capital-market access and stakeholder language. Industry examples and international-operation paragraphs are bodies, not separate factors.

- [prior source](https://www.sec.gov/Archives/edgar/data/773840/000077384025000010/hon-20241231.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 21/0/0; flags: none.
- [current source](https://www.sec.gov/Archives/edgar/data/773840/000077384026000013/hon-20251231.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 21/0/0; flags: none.

### Errors

No errors under the measured checks.

## INTC

Prior technology-development risk is merged into R&D/manufacturing risk; paragraphs on disaggregated design and process delays persist there. Foundry strategy is substantially reframed around Intel 14A. That continuity decision is unresolved and excluded from alignment scoring pending independent adjudication. U.S. government equity risk is added. Capital returns and corporate responsibility standalone factors are removed. Prior Risk Factors ends before Sales and Marketing, despite a shared chapter footer.

- [prior source](https://www.sec.gov/Archives/edgar/data/50863/000005086325000009/intc-20241228.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 24/0/0; flags: none.
- [current source](https://www.sec.gov/Archives/edgar/data/50863/000005086326000011/intc-20251227.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 22/0/0; flags: none.

### Errors

- {"category": "missing_link", "prior": "p03", "current": "c02", "prior_heading": "The development and implementation of new semiconductor products and manufacturing technologies are subject to many risks and uncertainties.", "current_heading": "We are making significant, long-term and inherently risky investments in R&D and manufacturing facilities that may not realize a favorable return."}
- {"category": "false_removed", "factor": "p03", "heading": "The development and implementation of new semiconductor products and manufacturing technologies are subject to many risks and uncertainties."}

## O

Most risks are reordered into new groups. New standalone factors cover loans, client financial stability and client/borrower/guarantor bankruptcy. ADA/fire/safety standalone factor is removed; similar regulation elsewhere does not by itself preserve factor identity.

- [prior source](https://www.sec.gov/Archives/edgar/data/726728/000072672825000055/o-20241231.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 34/0/0; flags: none.
- [current source](https://www.sec.gov/Archives/edgar/data/726728/000072672826000011/o-20251231.htm): boundary pass; heading starts precision 100.0%; recall 100.0%; TP/FP/FN 36/0/0; flags: none.

### Errors

No errors under the measured checks.
