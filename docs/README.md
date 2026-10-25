# Documentation

## Start here

- [Project overview and quickstart](../README.md): capabilities, local preview and pipeline setup.
- [Project status](PROJECT-STATUS.md): review branches, remaining work and acceptance criteria.
- [Architecture](ARCHITECTURE.md): stage boundaries, storage, offline behavior and frontend contract.
- [Methodology](METHODOLOGY.md): current algorithms, proposed scores and interpretation limits.
- [Runbook](RUNBOOK.md): commands, data refreshes, recovery, reviews and preview export.
- [Decisions](DECISIONS.md): implementation choices and tradeoffs.
- [Milestones](MILESTONES.md): delivery sequence and planned future scope.
- [Contributing](../CONTRIBUTING.md): reproductions, fixtures and validation expectations.

## Evaluation evidence

- [Pilot reference guide](../pipeline/tests/golden/README.md) and
  [frozen source-anchored labels](../pipeline/tests/golden/pilot.json).
- [Historical pre-fix report](EVALUATION-PILOT.md) and [JSON](evaluation-pilot.json).
- [Intel repair report](EVALUATION-INTEL-FIXED.md) and [JSON](evaluation-intel-fixed.json).
- [End-to-end Intel verification](INTEL-VALIDATION.md).
- [Remaining measured failures](EVALUATION-NEXT.md).

The pilot is a development dataset, not independently adjudicated ground truth
or a held-out benchmark. Preserve both historical and follow-up measurements.
