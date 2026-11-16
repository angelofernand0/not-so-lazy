# Shared Codex / Claude board

Board: https://github.com/angelofernand0/not-so-lazy/issues/11

The owner requested the OmniRiff board pattern with a tighter credit budget:
one small task total per hourly cycle, one active owner, at most 15 minutes of
work, and no further polling until the next hourly wake. These are work limits,
not a guarantee of a fixed token cost.

## Connect

Use the authenticated GitHub CLI (`gh`), as @angelofernand0. Never copy tokens.
Start a distinct worktree for each agent. Read AGENTS.md and CLAUDE.md.

```sh
BOARD_AGENT=codex bash board.sh whoami
BOARD_AGENT=codex bash board.sh unread
python3 tools/board_gate.py status --agent codex
# Substitute claude for BOTH agent settings in Claude Code.
```

The script defaults to this repository's issue #11. Read cursors are separate
per agent, including comments posted by the same human account. Set BOARD_AGENT
correctly before every board command. .board/ is ignored.

## Claim, work, finish

Only claim an explicitly queued, bounded task assigned to you. If the other
agent has not registered READY, do not claim it has joined or invent a handoff.

```sh
python3 tools/board_gate.py claim --agent codex --task 'N1: source-case inventory only'
BOARD_AGENT=codex bash board.sh post "[Angelo's Codex] CLAIM N1 — paths, acceptance checks, stop time"
# Perform this task only, with targeted checks. No second task this cycle.
BOARD_AGENT=codex bash board.sh post "[Angelo's Codex] DONE N1 — result, checks, commit/PR, next handoff"
python3 tools/board_gate.py finish --agent codex
```

The gate uses GitHub's atomic ref creation for a global active claim, immutable
hourly claim refs, and a rolling 60-minute start cooldown. Thus simultaneous
agents cannot both acquire work, including across a clock-hour boundary. It
uses ordinary authenticated GitHub requests and no model calls. Coordination
refs use the `nsl-agent-` tag prefix; do not manually move/delete them.

A local lease identifies the claim owner. `finish` refuses a different agent or
lease. Failed network requests stop work. An interrupted claim remains held and
blocks the next agent; ask the owner to review it rather than steal it. Deadlines
and task scope are agent instructions; the helper does not forcibly terminate a
model process or impose an account-level spending cap.

If work is incomplete after 15 minutes, post PARTIAL with the saved branch and
next step, then release your own lease. Resume the SAME queued task at a later
eligible cycle. A genuine blocker stays BLOCKED and held for review; do not
release it and let the other agent work around it silently.

## Schedule and stop behavior

This Codex chat has one hourly follow-up. Claude must have at most one hourly
schedule in its own app/session; setup is not complete until its actual readiness
and scheduling behavior are verified. Neither a board comment nor this file
can wake a stopped Claude session.

At each wake: check ACTIVE/PAUSED/DONE and new messages once; inspect unresolved
work/claim; if it is your turn, perform at most one task. If it is not your turn,
stop quietly. Do not poll until another response arrives. Prefer alternating
owners, with Codex first. Initial queue is on issue #11; queue exhausted means
stop and disable scheduling rather than invent more work.

The owner can post PAUSED/DONE or say stop in either controlling chat. Mirror
that status to the board; both agents must stop. No automatic production merges,
deploys, backfills, spending, credential changes or human-label adjudication.

## Verify the coordination helper

```sh
bash -n board.sh
python3 -m unittest discover -s tools -v
```

Tests cover rolling cooldowns, ownership checks, existing claims, failed atomic
acquisition and a cooldown race after locking. They never contact GitHub or an LLM.
