# Split/merge contract proposal — N1

Status: proposal for Claude's N2 review; no parsing, schema, matching, preview or
metric behavior changes. Evidence is the frozen [pilot manifest](../pipeline/tests/golden/pilot.json)
and [Intel-fixed run](evaluation-intel-fixed.json), not a new evaluation.
Reference IDs below are manifest-local IDs, not production risk-factor hashes.

## Five missing edges, four structural groups

The saved run reports 123 correct / 0 false / 5 missing continuity edges, four
false additions and two false removals. All ten section endpoint checks and
262 risk starts pass. Missing edges are structural correspondence problems;
heading detection does not need to be retuned for this task.

Microsoft sources: [prior FY2025](https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm)
(accession `0000950170-25-100235`) and
[current FY2026](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm)
(`0001193125-26-323660`), Item 1A.

1. **MSFT p02 → c02 and p02 → c03: two missing edges.** Prior heading:
   “Our focus on cloud-based and AI services presents execution and competitive risks.”
   Current c02 starts “Our cloud and AI strategy requires substantial investments”;
   c03 starts “Our success depends on our ability to develop, deliver, and maintain
   competitive cloud-based and AI products and services”. The reference split
   separates capital/demand strategy from product adoption/execution. Both current
   units are falsely added; p02 is falsely removed. There is no accepted anchor
   edge within this reference group.
2. **MSFT p11 → c14: one missing edge.** Prior infrastructure heading starts
   “We may have excessive outages, data losses, and disruptions of our online services”.
   Current c12 is “We may be unable to develop and expand adequate infrastructure.”;
   c14 starts “We may experience outages, disruptions, or capacity constraints”.
   Reference split: p11 → [c12, c14]. The p11 → c12 edge is already recovered;
   c14 is falsely added. Capacity expansion and reliable operations are distinct
   parts of the prior discussion.
3. **MSFT p12 → c15: one missing edge.** Prior: “We may experience supply or
   quality problems.” Current c13: “We may experience supply problems.” Current
   c15: “We may experience other quality problems.” Reference split:
   p12 → [c13, c15]. The p12 → c13 edge is recovered; c15 is falsely added.

Intel sources: [prior FY2024](https://www.sec.gov/Archives/edgar/data/50863/000005086325000009/intc-20241228.htm)
(`0000050863-25-000009`) and
[current FY2025](https://www.sec.gov/Archives/edgar/data/50863/000005086326000011/intc-20251227.htm)
(`0000050863-26-000011`), Item 1A.

4. **INTC p03 → c02: one missing edge.** Prior p03: “The development and
   implementation of new semiconductor products and manufacturing technologies
   are subject to many risks and uncertainties.” Reference merge:
   [p02, p03] → c02. Both p02 and c02 have the R&D/manufacturing-investment heading
   beginning “We are making significant, long-term and inherently risky investments”.
   The p02 → c02 edge is recovered, but p03 is falsely removed. The reference
   notes consolidation of process delays, yields, disaggregated designs and
   investment-return discussion into the current R&D/manufacturing unit.

Recovered anchor edges above follow from the complete reference relation minus
its listed missing edges, with no false links in the saved run. They should be
asserted explicitly against real matcher output in the implementation tests.

**Do not resolve INTC p04 ↔ c03.** The broad prior business/foundry strategy versus
current Intel 14A customer-specific risk remains an unresolved reference relation.
Its two endpoints stay excluded from measured truth. Do not silently promote it
to continuity, removal or addition to make the pilot look complete. All labels
remain agent-reviewed, not human-adjudicated or held out.

## Why an unmatched-only second pass is insufficient

`align.py` consumes endpoints when accepting a `Match(prior_id, current_id, ...)`.
Three of the four structural groups already contain an accepted anchor. Looking
only at leftover factors cannot discover those groups. A candidate pass must
consider one adjacent unmatched endpoint alongside an existing accepted pair,
while preserving the accepted edge and requiring additional body evidence.
Shared “cloud”, “AI”, “technology” or “infrastructure” words alone are inadequate.

## Minimal proposed output contract

Keep existing one-to-one matches and v1 diff/export payloads unchanged initially.
Return a **separate, deterministic candidate sidecar**, not fabricated extra
one-to-one rows or concatenated source text. Proposed fields:

```json
{
  "schema_version": 1,
  "relation_version": "structural-candidates-v1",
  "input_signature": "<upstream hashes and matcher/model/config versions>",
  "groups": [{
    "id": "<stable hash of kind and ordered production factor IDs>",
    "kind": "split",
    "prior_ids": ["<one production factor ID>"],
    "current_ids": ["<first factor ID>", "<second factor ID>"],
    "status": "candidate",
    "anchor_edges": [],
    "evidence": [{
      "side": "prior",
      "factor_id": "<production factor ID>",
      "start": 0,
      "end": 1,
      "text": "<exact source substring; schematic range only>"
    }],
    "reasons": ["<specific body correspondence evidence>"]
  }]
}
```

This JSON is an illustrative shape, not a valid source-evidence fixture or an
implemented API. Evidence text must equal the factor's original `text[start:end]`,
using half-open Unicode code-point offsets; provide evidence for every endpoint.
Model similarity, if included later, is an explained score, not a probability.

Initial bounds: exactly 1→2 or 2→1; unique IDs; existing risk-role factors only;
source order retained on each side; at most one existing anchor edge per group;
reject overlapping/conflicting groups instead of greedily selecting them.
Do not create many-to-many relations or consume accepted endpoints destructively.
Stable group IDs must not depend on mutable confidence values or iteration order.

Candidates **do not change** added/removed counts, moved badges, word spans or
public labels. Acceptance/promotion is a separate reviewed step. Once a reviewed
accepted-relation contract is agreed, its edges can enter evaluation by expanding
the group's prior/current Cartesian product (two edges for these bounded shapes).
A factor is structurally added/removed only if absent from all accepted continuity
edges; candidate groups alone must not suppress unmatched counts.

## Compatibility boundaries for N2

- `align.py`: singular endpoint Match records currently enforce one-to-one use.
  Preserve them as the baseline; do not append contradictory added/removed rows.
- `comparison.py` / `models.py`: stored alignments, digests and invalidation
  signatures assume singular endpoints. Sidecar prototype should avoid a migration;
  persistence/promotion needs a separately reviewed version/schema plan.
- `diff.py`: ranges reconstruct each original factor. Never diff concatenated
  group text and present those ranges as offsets in an individual source unit.
- `preview.py` and the frontend: v1 counts/cards and checksum/span validation
  must remain valid. Do not export a new relation kind into old consumers without
  an explicit versioned adapter and rendering/counting rules.
- `evaluate.py`: labels already model split/merge groups. Compare candidate
  proposals separately from accepted correspondence; never report candidate recall
  as accepted-alignment precision/recall. Preserve historical reports and label hash.

## Smallest proposed N3 slice (after N2 agreement)

Add a pure, offline **candidate representation and validation helper**, with
hand-constructed source-based cases for the three Microsoft splits and Intel
merge. Cover both all-unmatched and existing-anchor shapes, including unrelated
same-topic factors, overlapping groups, duplicate/unknown IDs, malformed cardinality
and invalid original-text evidence offsets. Return candidates only; no automatic
matcher promotion, database migration, preview regeneration or UI changes.

Done when the helper can represent all four frozen reference shapes without
mutating input Match/Factor objects, rejects ambiguous/malformed groups, and
preserves the Intel p04/c03 unresolved status. Targeted tests must assert the
existing anchor edges explicitly. This slice validates the contract, not discovery
accuracy; it does **not** fix the five missing edges by itself. Candidate generation
and accepted-relation integration require later, separately queued work.

N2 should review whether this sidecar boundary is compatible with current consumers
and whether the proposed slice fits one 15-minute work session. Return a narrower
slice if needed, plus the precise next task. No threshold choice or new accuracy
claim is made by this note.
