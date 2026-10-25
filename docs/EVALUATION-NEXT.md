# Work exposed by the five-pair pilot

The evaluation runs the current clean/extract/segment/align implementations from
raw cached sources, independently of the preview exporter and database. The
generated [report](EVALUATION-PILOT.md) and [full JSON](evaluation-pilot.json)
record exact counts, source checksums, label hash and component versions.
This is an agent-reviewed development baseline; independent human adjudication
and a held-out benchmark remain pending.

## 1. Fix Intel segmentation before ranking companies

All 262 labeled standalone risk starts are present in the predictions, but Intel
produces 320 additional paragraph-sized risk units (176 prior, 144 current).
The extra units account for all extra heading-start predictions in this sample.
Heading recall alone therefore hides a severe failure to group risk bodies.

Investigate the formatting handoff between the selected extraction and cleaned
HTML blocks. Intel's source headings are visually styled; the current segmenter
falls back to paragraphs when it cannot identify a structured heading inventory.
Add source-based regressions for full heading-plus-body units, not just heading
presence. Preserve paragraph fallback for genuinely unstructured sources, but
flag its use before presenting paragraph counts as risk-factor counts.

Do not tune embedding thresholds first: semantic matching of these fragmented
units yields 113 false continuity links in the pilot. Fix the segmentation input
and rerun the same frozen reference labels before comparing matchers.

## 2. Stop extraction at Intel's actual risk-section endpoint

The prior Intel filing's Risk Factors ends before “Sales and Marketing,” followed
by other chapter content. The selected extraction includes subsequent material;
the measured suffix check fails even though current automated flags are empty.
Nine of ten boundary checks pass overall. Add an explicit cross-reference/layout
regression with the reviewed endpoint. Do not change the label to fit the parser.
The current Intel filing has a distinct “Other Key Information” boundary.

## 3. Account for splits and merges

Microsoft's cloud/AI, infrastructure and supply/quality discussions become
multiple current factors; Intel consolidates technology-development discussion
into its R&D/manufacturing factor. A one-to-one matcher cannot recover every
labeled continuity edge. The baseline misses five reference edges, including
four for Microsoft and one for Intel.

After segmentation is fixed, evaluate a bounded split/merge second pass and
distinguish structural changes from newly introduced or removed standalone risks.
Keep source evidence visible and low-confidence decisions reviewable. Intel's
broad prior foundry strategy versus current Intel 14A factor is explicitly
unresolved; two reference endpoints are excluded, not silently treated as truth.

## 4. Expand and adjudicate before public accuracy claims

Apple, Honeywell and Realty Income have no errors under the pilot's measured
heading-start, boundary-anchor and continuity checks. This does not establish
exact factor-body accuracy, correct word diffs, economic significance or
population-wide performance. The pilot intentionally includes tricky layouts.

Have a human independently check the reference headings and continuity decisions,
resolve ambiguous cases, then expand to 30 diverse pairs. Include banks, spin-offs,
amendments and fiscal-year transitions. Reserve an untouched subset before tuning.
Only then use the results to gate a full-universe leaderboard. Keep Brain
correlation separate from parser correctness and compare equivalent periods.
